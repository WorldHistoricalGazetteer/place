import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import PriorityQueue

import epitran
import epitran.vector

sys.path.append('/usr/local/share/epitran')  # This is where dictionaries are stored by the Dockerfile
from iso639 import ISO_639_1_TO_3, ISO_639_3
from epitran_languages import EPITRAN_LANGS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PhoneticsProcessor:
    """Processor class responsible for phonetic processing using Epitran."""

    def __init__(self):
        self.epitran_instances = {}
        self.vector_instances = {}
        self.task_queue = PriorityQueue()
        self.results = {}
        self.task_id_counter = 1
        self.executor = ThreadPoolExecutor(max_workers=5)

    def init_epitran_instances(self):
        """Initialise Epitran instances for all supported languages."""
        for lang_script in EPITRAN_LANGS.keys():
            self.epitran_instances[lang_script] = epitran.Epitran(lang_script)
            self.vector_instances[lang_script] = epitran.vector.VectorsWithIPASpace(lang_script, [lang_script])

    def process_toponym(self, toponym, lang_script, priority, to_index=False):
        """Generate phonetic representations using Epitran."""
        task_id = self.task_id_counter
        self.task_id_counter += 1

        # Create an event for notifying when the task is done
        event = threading.Event()

        # Add the task to the priority queue with its event
        self.task_queue.put((priority, task_id, toponym, lang_script, event, to_index))

        # Start processing the task asynchronously
        self.executor.submit(self._process_task, task_id, event)

        return task_id, event

    def _process_task(self, task_id, event):
        """Process a task in the queue."""
        priority, _, toponym, lang_script, _, to_index = self.task_queue.get()

        # Initialise Epitran instance for the given language if not included in default set or previously used
        if lang_script not in self.epitran_instances:
            self.epitran_instances[lang_script] = epitran.Epitran(lang_script)

        # Process the toponym
        ipa = self.epitran_instances[lang_script].transliterate(toponym)
        tuples = self.epitran_instances[lang_script].word_to_tuples(toponym)
        segs = (
            self.vector_instances[lang_script].word_to_segs(toponym)
            if lang_script in self.vector_instances
            else None
        )

        if to_index:
            # TODO: Store phonetic representations in Vespa
            pass

        # Store the result
        self.results[task_id] = {
            "toponym": toponym,
            "ipa": ipa,
            "tuples": tuples,
            **({"segs": segs} if segs else {}),
            "lang": lang_script,
        }

        # Start the cleanup timer after the result is ready
        threading.Timer(30, self._cleanup_result, [task_id]).start()

        # Signal that the task is completed
        event.set()

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
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests to fetch deferred results."""
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
            toponym, lang_639_3, script, priority = self._parse_request()

            # Query Vespa for phonetic representations
            # TODO: Implement Vespa exact match query here and return the results if phonetic representations found
            to_index = False  # Set to True if toponym is found without phonetic representations

            # If phonetic representations not found in Vespa, process the toponym using Epitran
            task_id, event = self.processor.process_toponym(toponym, f"{lang_639_3}-{script}", priority, to_index)

            # Wait for the result for up to 1 second # TODO: Increase timeout if needed - how fast is Epitran?
            event.wait(timeout=1)

            result = self.processor.get_result(task_id)

            if result:
                result.pop("tuples", None)
                result.pop("segs", None)
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

        return toponym, lang_639_3, script, priority

    def _send_response(self, status_code, response_data):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())


if __name__ == "__main__":
    # Initialise Epitran instances
    processor = PhoneticsProcessor()
    processor.init_epitran_instances()

    # Start the HTTP server
    server_address = ("", 8000)
    httpd = HTTPServer(server_address, PhoneticsHandler)
    logger.info("Starting server on port 8000...")
    httpd.serve_forever()
