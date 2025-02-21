import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from itertools import count
from queue import PriorityQueue

import epitran
import epitran.vector
from vespa.application import Vespa, VespaAsync, VespaSync

from epitran_languages import EPITRAN_LANGS
from iso639 import ISO_639_1_TO_3, ISO_639_3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vespa_host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}


def escape_yql(text: str) -> str:
    """
    Quote " and backslash \ characters in text values must be escaped by a backslash
    See: https://docs.vespa.ai/en/reference/query-language-reference.html
    """
    return re.sub(r'[\\"]', r"\\\g<0>", text)


class PhoneticsProcessor:
    """Processor class responsible for phonetic processing using Epitran."""

    def __init__(self):
        self.epitran_instances = {}
        self.vector_instances = {}
        self.instance_timers = {}
        self.task_queue = PriorityQueue()
        self.results = {}
        self.task_id_counter = count(1)
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.vespa_feed_async_app = VespaAsync(Vespa(url=vespa_host_mapping["feed"]))
        self.lock = threading.Lock()

    def _prepare_epitran_instance(self, lang_script):
        """Create an Epitran instance if not already created."""
        with self.lock:
            if lang_script not in self.epitran_instances:
                self.epitran_instances[lang_script] = epitran.Epitran(lang_script)
                if lang_script in EPITRAN_LANGS.keys():
                    self.vector_instances[lang_script] = epitran.vector.VectorsWithIPASpace(lang_script, [lang_script])

            # If there's an existing timer, cancel it
            if lang_script in self.instance_timers:
                self.instance_timers[lang_script].cancel()

            # Set a new timer to remove the instance after 1 hour
            timer = threading.Timer(3600, self._remove_epitran_instance, [lang_script])
            timer.start()

            # Store the new timer reference
            self.instance_timers[lang_script] = timer

    def _remove_epitran_instance(self, lang_script):
        """Remove the Epitran instance after 1 hour."""
        if lang_script in self.epitran_instances:
            del self.epitran_instances[lang_script]
            if lang_script in EPITRAN_LANGS.keys():
                del self.vector_instances[lang_script]
            del self.instance_timers[lang_script]
            logger.info(f"Removed Epitran instance for {lang_script} after 1 hour.")

    def process_toponym(self, toponym, lang_script, priority, toponym_id=None):
        """Generate phonetic representations using Epitran."""
        task_id = next(self.task_id_counter)

        # Create an event for notifying when the task is done
        event = threading.Event()

        # Add the task to the priority queue with its event
        self.task_queue.put((priority, task_id, toponym, lang_script, event, toponym_id))

        # Start processing a task asynchronously
        self.executor.submit(self._process_task)

        return task_id, event

    def _process_task(self):
        """Process a task in the queue."""
        _, task_id, toponym, lang_script, event, toponym_id = self.task_queue.get()
        try:

            # Initialise Epitran instances (unless already initialised and not expired)
            self._prepare_epitran_instance(lang_script)

            # Process the toponym
            fields = {
                "toponym": toponym,
                "ipa": self.epitran_instances[lang_script].transliterate(toponym),
                "tuples": self.epitran_instances[lang_script].word_to_tuples(toponym),
                **({"segs": segs} if
                   (segs := self.vector_instances[lang_script].word_to_segs(
                       toponym) if lang_script in EPITRAN_LANGS.keys() else None)
                   is not None else {}),
                "lang": lang_script,
            }

            # Store the result (cannot rely on index if toponym is not indexed)
            self.results[task_id] = fields

            # Start the cleanup timer after the result is ready
            threading.Timer(30, self._cleanup_result, [task_id]).start()

            # Signal that the task is completed
            event.set()

            if toponym_id:
                self.vespa_feed_async_app.feed_data_point(schema="toponym", data_id=toponym_id, fields=fields)

        finally:
            self.task_queue.task_done()

    def _cleanup_result(self, task_id):
        """Remove the result from memory if it hasn't been fetched."""
        if task_id in self.results:
            logger.info(f"Cleaning up result for task_id {task_id}")
            del self.results[task_id]

    def get_result(self, task_id):
        """Get the result for a task."""
        result = self.results.pop(task_id, None)  # Remove the result once fetched
        return result


class PhoneticsHandler(BaseHTTPRequestHandler):
    """HTTP Handler class responsible for processing HTTP requests."""

    def __init__(self, *args, **kwargs):
        self.processor = PhoneticsProcessor()
        self.vespa_query_sync_app = VespaSync(Vespa(url=vespa_host_mapping["query"]))
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests to fetch deferred results or clear the queue."""
        if self.path == "/clear_queue":
            # Clear the task queue
            self.processor.task_queue.queue.clear()
            self._send_response(200, {"message": "Queue cleared"})
        else:
            try:
                # Parse task_id from the URL path
                task_id = int(self.path.strip("/"))

                # Fetch the result
                result = self.processor.get_result(task_id)

                if result:
                    self._send_response(200, result)
                else:
                    self._send_response(404, {"error": "Task not found or expired"})

            except ValueError:
                self._send_response(400, {"error": "Invalid task_id"})
            except Exception as e:
                logger.error(f"Error processing GET request: {e}", exc_info=True)
                self._send_response(500, {"error": "Internal Server Error"})

    def do_POST(self):
        try:
            toponym, lang_639_3, script, priority, refresh = self._parse_request()

            if not refresh:
                # Query Vespa for phonetic representations
                vespa_result = self._query_vespa(toponym, lang_639_3, script)
                if vespa_result.get("fields", {}).get("ipa"):
                    self._send_response(200, vespa_result)
                    return
            else:
                vespa_result = {}

            # If phonetic representations not found in Vespa, process the toponym using Epitran
            toponym_id = vespa_result.get("document_id", None)
            task_id, event = self.processor.process_toponym(toponym, f"{lang_639_3}-{script}", priority, toponym_id)

            # Wait for the result for up to 3 seconds # TODO: Increase timeout if needed - how fast is Epitran?
            event.wait(timeout=3)

            result = self.processor.get_result(task_id)

            if result:
                self._send_response(200, result)
            else:
                # If result is not ready within 1 second, return the task id and queue length
                queue_length = self.processor.task_queue.qsize()
                self._send_response(202, {"task_id": task_id, "queue_length": queue_length})

        except ValueError as e:
            self._send_response(400, {"error": str(e)})
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            self._send_response(500, {"error": "Internal Server Error"})

    def _parse_request(self):
        """Parse and validate the incoming JSON request."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            request_json = json.loads(post_data)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON")

        toponym = request_json.get("toponym")
        if not toponym:
            raise ValueError("Missing required 'toponym' field")

        language = request_json.get("lang", "eng")
        lang_639_3 = (
            # Check that it's a valid 3-letter code
            language if len(language) == 3 and language in ISO_639_3
            # Otherwise try to convert from 2-letter code
            else ISO_639_1_TO_3.get(language, {}).get("639-3")
        )
        if not lang_639_3:
            raise ValueError(f"Invalid or unsupported language code: {language}")

        script = request_json.get("script", "Latn")

        priority = request_json.get("priority", 0)

        refresh = "refresh" in request_json

        return toponym, lang_639_3, script, priority, refresh

    def _query_vespa(self, toponym, lang_639_3, script):
        """Check if the phonetic representation already exists in Vespa."""
        yql = f'SELECT * FROM toponym WHERE name_strict="{escape_yql(toponym)}" AND bcp47_language="{lang_639_3}" AND bcp47_script="{script}" LIMIT 1;'
        response = self.vespa_query_sync_app.query({'yql': yql})
        response_root = response.get_json().get("root", {})

        if errors := response_root.get("errors"):
            return {"error": errors}
        if response_root.get("fields", {}).get("totalCount", 0) == 0:
            return {}
        document = (
            response_root.get("children", [{}])[0]
            .get("fields", {})
        )
        return {
            "document_id": document.get("documentid", "").split("::")[-1],
            "fields": document,
        }

    def _send_response(self, status_code, response_data):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())


if __name__ == "__main__":
    # Start the HTTP server
    server_address = ("", 8000)
    httpd = HTTPServer(server_address, PhoneticsHandler)
    logger.info("Starting server on port 8000...")
    httpd.serve_forever()
