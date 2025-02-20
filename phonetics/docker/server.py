import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import epitran
import epitran.vector

sys.path.append('/usr/local/share/epitran') # This is where dictionaries are stored by the Dockerfile
from iso639 import ISO_639_2_TO_3
from epitran_languages import EPITRAN_LANGS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PhoneticsHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Call the parent class constructor
        self.epitran_instances = {lang_script: epitran.Epitran(lang_script) for lang_script in EPITRAN_LANGS.keys()}
        self.vector_instances = {lang_script: epitran.vector.VectorsWithIPASpace(lang_script, [lang_script]) for lang_script in EPITRAN_LANGS.keys()}

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        toponym = None

        try:
            request_json = json.loads(post_data)
            toponym = request_json.get("toponym")
            lang_639_2 = request_json.get("lang", "en")
            script = request_json.get("script", "Latn")

            if not toponym:
                self._send_response(400, {"error": "Missing required 'toponym' field"})
                return

            lang_639_3 = ISO_639_2_TO_3.get(lang_639_2, {}).get("639-3", None)
            if not lang_639_3:
                self._send_response(400, {"error": f"Invalid or unsupported language code: {lang_639_2}"})
                return
            lang_script = f"{lang_639_3}-{script}"

            if not lang_script in self.epitran_instances:
                self.epitran_instances[lang_script] = epitran.Epitran(lang_script)
            ipa = self.epitran_instances[lang_script].transliterate(toponym)
            tuples = self.epitran_instances[lang_script].word_to_tuples(toponym)

            self._send_response(200, {
                "toponym": toponym,
                "ipa": ipa,
                "tuples": tuples,
                **({"segs": self.vector_instances[lang_script].word_to_segs(toponym)} if lang_script in self.vector_instances else {}),
                "lang": lang_script
            })

        except json.JSONDecodeError:
            self._send_response(400, {"error": "Invalid JSON"})
        except Exception as e:
            logger.error(f"Failed to generate phonetics for {toponym}: {e}", exc_info=True)
            self._send_response(500, {"error": "Internal Server Error"})

    def _send_response(self, status_code, response_data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())


if __name__ == "__main__":
    handler = PhoneticsHandler

    server_address = ("", 8000)
    httpd = HTTPServer(server_address, handler)
    logger.info("Starting server on port 8000...")
    httpd.serve_forever()
