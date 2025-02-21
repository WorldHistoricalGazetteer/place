import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import epitran
import epitran.vector

sys.path.append('/usr/local/share/epitran')  # This is where dictionaries are stored by the Dockerfile
from iso639 import ISO_639_1_TO_3, ISO_639_3
from epitran_languages import EPITRAN_LANGS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PhoneticsHandler(BaseHTTPRequestHandler):
    epitran_instances = {}
    vector_instances = {}

    @classmethod
    def init_epitran_instances(cls):
        """Initialise Epitran instances for all supported languages."""
        for lang_script in EPITRAN_LANGS.keys():
            cls.epitran_instances[lang_script] = epitran.Epitran(lang_script)
            cls.vector_instances[lang_script] = epitran.vector.VectorsWithIPASpace(lang_script, [lang_script])

    def do_POST(self):
        try:
            toponym, lang_639_3, script = self._parse_request()

            # Query Vespa for phonetic representations
            # TODO: Implement Vespa exact match query here and return the results if phonetic representations found

            # If phonetic representations not found in Vespa, process the toponym using Epitran
            result = self._process_toponym(toponym, f"{lang_639_3}-{script}")
            # TODO: If the toponym exists in Vespa but lacks phonetic representations, index the result

            # Drop segs and tuples from the returned result
            result.pop("tuples", None)
            result.pop("segs", None)
            self._send_response(200, result)

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

        return toponym, lang_639_3, script

    def _process_toponym(self, toponym, lang_script):
        """Generate phonetic representations using Epitran."""
        if lang_script not in self.epitran_instances:
            self.epitran_instances[lang_script] = epitran.Epitran(lang_script)

        ipa = self.epitran_instances[lang_script].transliterate(toponym)
        tuples = self.epitran_instances[lang_script].word_to_tuples(toponym)
        segs = (
            self.vector_instances[lang_script].word_to_segs(toponym)
            if lang_script in self.vector_instances
            else None
        )

        return {
            "toponym": toponym,
            "ipa": ipa,
            "tuples": tuples,
            **({"segs": segs} if segs else {}),
            "lang": lang_script,
        }

    def _send_response(self, status_code, response_data):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())


if __name__ == "__main__":
    # Initialise Epitran instances
    PhoneticsHandler.init_epitran_instances()

    # Start the HTTP server
    server_address = ("", 8000)
    # noinspection PyTypeChecker
    httpd = HTTPServer(server_address, PhoneticsHandler)
    logger.info("Starting server on port 8000...")
    httpd.serve_forever()
