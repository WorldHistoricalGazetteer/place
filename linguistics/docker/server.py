import logging
import os
import re
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from itertools import count
from queue import PriorityQueue

import epitran
import epitran.vector
import icu
import numpy
import numpy as np
import orjson
import panphon
from vespa.application import Vespa, VespaAsync, VespaSync

from iso15924 import ISO_15924
from iso639 import ISO_639_1_TO_3, ISO_639_3

EPITRAN_LANGS = {}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vespa_host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}


def make_json_serializable(obj):
    """
    Recursively converts a data structure to a JSON-serializable format.
    Handles lists, tuples, dictionaries, NumPy arrays, and map objects.
    """
    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, numpy.ndarray):
        return obj.tolist()
    elif isinstance(obj, map):
        return list(obj)  # Convert map objects to lists
    else:
        return obj  # Return other objects as is


def generate_epitran_langs():
    global EPITRAN_LANGS
    # Get the directory where Epitran stores its mapping files
    data_dir = os.path.join(os.path.dirname(epitran.__file__), "data", "map")

    # List all files in the directory
    module_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]

    # Extract module names by removing the ".csv" extension
    module_names = [os.path.splitext(f)[0] for f in module_files]

    # Add eng-Latn, cmn-Hans, and cmn-Hant (implemented via additional modules in Dockerfile rather than with .csv mapping files)
    module_names.extend(["eng-Latn", "cmn-Hans", "cmn-Hant"])

    # Populate EPITRAN_LANGS dictionary
    for mod in sorted(module_names):
        mod_parts = mod.split("-")

        # Lookup language name from ISO_639_3
        language_name = ISO_639_3.get(mod_parts[0], {}).get("ref_name", "Unknown Language")

        # Lookup script name from ISO_15924
        script_name = ISO_15924.get(mod_parts[1], "Unknown Script") if len(mod_parts) > 1 else "Unknown Script"

        EPITRAN_LANGS[mod] = f"{language_name} ({script_name})"


def escape_yql(text: str) -> str:
    """
    Quote " and backslash \ characters in text values must be escaped by a backslash
    See: https://docs.vespa.ai/en/reference/query-language-reference.html
    """
    return re.sub(r'[\\"]', r"\\\g<0>", text)


def detect_script(text: str) -> str:
    """
    Detects the script of a given text using ICU.
    Returns the 4-letter ISO 15924 script code.
    """
    scripts = {}
    for char in text:
        try:
            script_name = icu.Script.getScript(char).getShortName()
            scripts[script_name] = scripts.get(script_name, 0) + 1
        except icu.ICUError:
            pass  # Handle potential errors gracefully (e.g., for non-assigned characters)

    # Return the most common script or default to "Latn"
    return max(scripts, key=scripts.get, default="Latn")


def convert_panphon(feature_vectors):
    """
    Converts PanPhon feature vectors from symbolic to numeric representation.
    """
    # Convert to NumPy array for efficient operations
    np_vectors = np.array(feature_vectors, dtype=object)

    # Create a mask for '-' and '+' symbols
    minus_mask = np_vectors == '-'
    zero_mask = np_vectors == '0'
    plus_mask = np_vectors == '+'

    # Use the masks to assign -1 and 1 where appropriate
    np_vectors[minus_mask] = -1
    np_vectors[zero_mask] = 0
    np_vectors[plus_mask] = 1

    # Convert the array back to a list of lists
    return np_vectors.astype(int).tolist()


class PhoneticsProcessor:
    """Processor class responsible for phonetic processing using Epitran."""

    def __init__(self):
        self.epitran_instances = {}
        self.instance_timers = {}
        self.task_queue = PriorityQueue()
        self.results = {}
        self.task_id_counter = count(1)
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.vespa_feed_async_app = VespaAsync(Vespa(url=vespa_host_mapping["feed"]))
        self.lock = threading.Lock()
        self.ft = panphon.FeatureTable()

    def _generate_embeddings(self, ipa, max_length=30, max_ngram=5):
        try:
            ipa_truncated = ipa[:max_length]
            ipa_unicode = [ord(ipa_character) for ipa_character in ipa_truncated]
            ipa_length = len(ipa_unicode)

            ngrams = []
            for n in range(2, max_ngram + 1):
                for i in range(ipa_length - n + 1):
                    ngrams.append(ipa_unicode[i: i + n])
                # Pad to max_length with space_unicode arrays of length n to ensure alignment
                ngrams = ngrams + [np.zeros(n, dtype=int)] * (max_length - ipa_length)

            return {
                "ngram": ngrams,
                "phonetic": convert_panphon(self.ft.word_to_vector_list(ipa_truncated)),
                # No need to pad a Vespa dense tensor
            }

        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(
                f"Error generating combined embedding: {e}", exc_info=True
            )
            return {
                "error": f"Internal Server Error ({e})",
                "traceback": error_trace.split("\n")  # Convert to list for better readability in JSON
            }

    def _prepare_epitran_instance(self, lang_script):
        """
        Create an Epitran instance if not already created.

        Keeping instances alive reduces the overhead in loading phonetic space definitions during initialization.
        """
        with self.lock:
            if lang_script not in self.epitran_instances:
                self.epitran_instances[lang_script] = epitran.Epitran(lang_script)

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

            # Generate IPA string
            ipa = self.epitran_instances[lang_script].transliterate(toponym)

            # Process the toponym
            fields = {
                "toponym": toponym,
                "ipa": ipa,
                "embeddings": self._generate_embeddings(ipa),
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
                    self._send_response(404, {"error": f"Task #{task_id} not found."})

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
                # If result is not ready within 3 seconds, return the task id and queue length
                queue_length = self.processor.task_queue.qsize()
                self._send_response(202, {"task_id": task_id, "queue_length": queue_length})

        except ValueError as e:
            self._send_response(400, {"error": str(e)})
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"Error processing request: {e}", exc_info=True)
            self._send_response(500, {
                "error": f"Internal Server Error ({e})",
                "traceback": error_trace.split("\n")  # Convert to list for better readability in JSON
            })

    def _parse_request(self):
        """Parse and validate the incoming JSON request."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            request_json = orjson.loads(post_data)
        except orjson.JSONDecodeError:
            raise ValueError("Invalid JSON")

        toponym = request_json.get("toponym")
        if not toponym:
            raise ValueError("Missing required 'toponym' field")

        language = request_json.get("lang", "eng")
        lang_639_3 = (
            # Check that it's a valid 3-letter code
            language if len(language) == 3 and language in ISO_639_3
            # Otherwise try to convert from 2-letter code: default to 'eng' if not found
            else ISO_639_1_TO_3.get(language, {}).get("639-3", "eng")
        )

        script = request_json.get("script", detect_script(toponym))

        lang_script = f"{lang_639_3}-{script}"

        if not lang_script in EPITRAN_LANGS.keys():
            raise ValueError(f"Unsupported language-script combination: {lang_script}")

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

        # Make the response data JSON serializable
        serializable_data = make_json_serializable(response_data)

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(orjson.dumps(serializable_data))


if __name__ == "__main__":
    # Generate Epitran language mappings
    generate_epitran_langs()

    # Run some tests to verify the script detection
    print("Hello, world! ->", detect_script("Hello, world!"))
    print("こんにちは、世界！ ->", detect_script("こんにちは、世界！"))
    print("Привет, мир! ->", detect_script("Привет, мир!"))
    print("مرحبا بالعالم! ->", detect_script("مرحبا بالعالم!"))
    print("नमस्ते, दुनिया! ->", detect_script("नमस्ते, दुनिया!"))
    print("ᜋᜄ᜔ᜆᜓ, ᜋᜄ᜔ᜆᜓ! ->", detect_script("ᜋᜄ᜔ᜆᜓ, ᜋᜄ᜔ᜆᜓ!"))
    print("你好，世界！ ->", detect_script("你好，世界！"))
    print("안녕하세요, 세계! ->", detect_script("안녕하세요, 세계!"))

    # Start the HTTP server
    server_address = ("", 8000)
    httpd = HTTPServer(server_address, PhoneticsHandler)
    logger.info("Starting server on port 8000...")
    httpd.serve_forever()
