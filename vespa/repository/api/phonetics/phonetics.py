import logging

import epitran
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PhoneticsRequest(BaseModel):
    toponym: str
    lang: str = "en"
    script: str
    vector: bool = False

    class Config:
        schema_extra = {
            "example": {
                "toponym": "London",
                "lang": "en",
                "script": "Latn",
                "vector": False
            }
        }


# Language mappings: TODO: extend to convert 2-letter ISO 639-1 codes to 3-letter ISO 639-3 codes
EPITRAN_LANGS = {
    "en": "eng-Latn",
    "zh": "cmn-Hans"
}


class PhoneticProcessor:
    def __init__(self):
        self.epitran_instances = {}

    def get_phonetics(self, payload: PhoneticsRequest) -> dict:
        toponym, lang, script = payload
        try:

            # Convert 2-letter to 3-letter code if needed
            lang_code = ISO639_1_TO_3.get(lang, lang)

            # Generate Epitran key (e.g., "eng-Latn")
            epi_key = f"{lang_code}-{script}"

            # Validate and load Epitran instance
            if epi_key not in EPITRAN_LANGS.values():
                raise HTTPException(status_code=400, detail=f"Unsupported language/script combination: {epi_key}")

            if epi_key not in self.epitran_instances:
                self.epitran_instances[epi_key] = epitran.Epitran(epi_key)

            # Convert to IPA
            return self.epitran_instances[epi_key].transliterate(toponym)

        except Exception as e:
            logger.error(f"Error processing IPA for {toponym} ({lang}, {script}): {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"IPA generation failed: {str(e)}")


phonetic_processor = PhoneticProcessor()
