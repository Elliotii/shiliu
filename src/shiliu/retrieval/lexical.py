"""Pinned document-frequency-preserving jieba profile and safe OR tsquery."""

from hashlib import sha256
from pathlib import Path
import unicodedata
import jieba

DICTIONARY_SHA256 = "7197c3211ddd98962b036cdf40324d1ea2bfaa12bd028e68faa70111a88e12a8"


class F1Tokenizer:
    def __init__(self, cache_dir=None):
        if jieba.__version__ != "0.42.1":
            raise RuntimeError("jieba_version_mismatch")
        dictionary = Path(jieba.__file__).with_name("dict.txt")
        self.dictionary_hash = sha256(dictionary.read_bytes()).hexdigest()
        if self.dictionary_hash != DICTIONARY_SHA256:
            raise RuntimeError("jieba_dictionary_hash_mismatch")
        self.profile = f"jieba-0.42.1-nfkc-casefold-hmm0-{self.dictionary_hash}"
        self.engine = jieba.Tokenizer(str(dictionary))
        if cache_dir is not None:
            cache_dir = Path(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.engine.tmp_dir = str(cache_dir)
            self.engine.cache_file = "jieba-" + self.dictionary_hash + ".cache"
        self.engine.initialize()

    def tokens(self, value):
        result = []
        for word in self.engine.cut(
            unicodedata.normalize("NFKC", value).casefold(), HMM=False
        ):
            run = ""
            for character in word:
                category = unicodedata.category(character)
                if category[0] in "LN" or category == "Co":
                    run += character
                elif run:
                    result.append(run)
                    run = ""
            if run:
                result.append(run)
        return result

    def document(self, value):
        return " ".join(self.tokens(value))

    def query(self, value):
        # Terms are data passed as a single SQL parameter. Token characters never
        # contain tsquery punctuation; quoting is retained as a second boundary.
        return " | ".join(
            "'" + term.replace("\\", "\\\\").replace("'", "''") + "'"
            for term in dict.fromkeys(self.tokens(value))
        )
