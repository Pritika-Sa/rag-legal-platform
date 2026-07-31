"""
Adapted from AI4Bharat's IndicTrans2 reference CTranslate2 inference engine
(https://github.com/AI4Bharat/IndicTrans2, inference/engine.py, MIT
licensed). Trimmed to just the pieces this app needs (single-sentence-unit
batch translation — the "View in Tamil" feature always hands this
already-segmented UI strings, never raw paragraphs, so the original's
paragraph/sentence-splitting layer and the alternate fairseq backend were
dropped) and renamed to match this project's module layout.
"""
import os

from indicnlp.normalize import indic_normalize
from indicnlp.tokenize import indic_tokenize, indic_detokenize
from indicnlp.transliterate import unicode_transliterate
from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
import sentencepiece as spm

from .flores_codes import flores_codes
from .normalize_punctuation import punc_norm
from .normalize_regex import normalize


def add_token(sent, src_lang, tgt_lang, delimiter=" "):
    return src_lang + delimiter + tgt_lang + delimiter + sent


def apply_lang_tags(sents, src_lang, tgt_lang):
    return [add_token(s.strip(), src_lang, tgt_lang) for s in sents]


def truncate_long_sentences(sents, placeholder_entity_map_sents):
    """Splits any sentence longer than the model's per-chunk budget into
    multiple chunks. Also returns group_sizes (length == len(sents)) so
    callers can reassemble one output per original input — a full legal
    clause easily exceeds 256 SPM subword pieces, so this expansion is a
    realistic case here, not just an edge case."""
    MAX_SEQ_LEN = 256
    new_sents = []
    placeholders = []
    group_sizes = []
    for j, sent in enumerate(sents):
        words = sent.split()
        if len(words) > MAX_SEQ_LEN:
            chunks = []
            i = 0
            while i <= len(words):
                chunks.append(" ".join(words[i:i + MAX_SEQ_LEN]))
                i += MAX_SEQ_LEN
            placeholders.extend([placeholder_entity_map_sents[j]] * len(chunks))
            new_sents.extend(chunks)
            group_sizes.append(len(chunks))
        else:
            placeholders.append(placeholder_entity_map_sents[j])
            new_sents.append(sent)
            group_sizes.append(1)
    return new_sents, placeholders, group_sizes


class Model:
    def __init__(self, ckpt_dir, device="cpu", beam_size=5):
        self.ckpt_dir = ckpt_dir
        self.beam_size = beam_size
        self.en_tok = MosesTokenizer(lang="en")
        self.en_normalizer = MosesPunctNormalizer()
        self.en_detok = MosesDetokenizer(lang="en")
        self.xliterator = unicode_transliterate.UnicodeIndicTransliterator()

        self.sp_src = spm.SentencePieceProcessor(model_file=os.path.join(ckpt_dir, "vocab", "model.SRC"))
        self.sp_tgt = spm.SentencePieceProcessor(model_file=os.path.join(ckpt_dir, "vocab", "model.TGT"))

        import ctranslate2
        self.translator = ctranslate2.Translator(self.ckpt_dir, device=device)

    def ctranslate2_translate_lines(self, lines):
        tokenized_sents = [x.strip().split(" ") for x in lines]
        translations = self.translator.translate_batch(
            tokenized_sents, max_batch_size=9216, batch_type="tokens",
            max_input_length=160, max_decoding_length=256, beam_size=self.beam_size,
        )
        return [" ".join(x.hypotheses[0]) for x in translations]

    def batch_translate(self, batch, src_lang, tgt_lang):
        preprocessed_sents, placeholder_entity_map_sents, group_sizes = self.preprocess_batch(batch, src_lang, tgt_lang)
        translations = self.ctranslate2_translate_lines(preprocessed_sents)
        postprocessed = self.postprocess(translations, placeholder_entity_map_sents, tgt_lang)

        # Regroup chunks back into exactly one string per original input
        # (see truncate_long_sentences) so callers always get back a list
        # the same length as `batch` — without this, a long input that got
        # split into N chunks would silently misalign every translation
        # after it when callers zip results against their original inputs.
        result = []
        idx = 0
        for size in group_sizes:
            result.append(" ".join(postprocessed[idx:idx + size]))
            idx += size
        return result

    def preprocess_batch(self, batch, src_lang, tgt_lang):
        preprocessed_sents, placeholder_entity_map_sents = self.preprocess(batch, lang=src_lang)
        tokenized_sents = self.apply_spm(preprocessed_sents)
        tokenized_sents, placeholder_entity_map_sents, group_sizes = truncate_long_sentences(
            tokenized_sents, placeholder_entity_map_sents
        )
        return apply_lang_tags(tokenized_sents, src_lang, tgt_lang), placeholder_entity_map_sents, group_sizes

    def apply_spm(self, sents):
        return [" ".join(self.sp_src.encode(sent, out_type=str)) for sent in sents]

    def preprocess_sent(self, sent, normalizer, lang):
        iso_lang = flores_codes[lang]
        sent = punc_norm(sent, iso_lang)
        sent, placeholder_entity_map = normalize(sent)

        transliterate = True
        if lang.split("_")[1] in ["Arab", "Aran", "Olck", "Mtei", "Latn"]:
            transliterate = False

        if iso_lang == "en":
            processed_sent = " ".join(self.en_tok.tokenize(self.en_normalizer.normalize(sent.strip()), escape=False))
        elif transliterate:
            processed_sent = self.xliterator.transliterate(
                " ".join(indic_tokenize.trivial_tokenize(normalizer.normalize(sent.strip()), iso_lang)),
                iso_lang, "hi",
            ).replace(" ् ", "्")
        else:
            processed_sent = " ".join(indic_tokenize.trivial_tokenize(normalizer.normalize(sent.strip()), iso_lang))

        return processed_sent, placeholder_entity_map

    def preprocess(self, sents, lang):
        processed_sents, placeholder_entity_map_sents = [], []
        if lang == "eng_Latn":
            normalizer = None
        else:
            normalizer = indic_normalize.IndicNormalizerFactory().get_normalizer(flores_codes[lang])
        for sent in sents:
            sent, placeholder_entity_map = self.preprocess_sent(sent, normalizer, lang)
            processed_sents.append(sent)
            placeholder_entity_map_sents.append(placeholder_entity_map)
        return processed_sents, placeholder_entity_map_sents

    def postprocess(self, sents, placeholder_entity_map, lang, common_lang="hin_Deva"):
        lang_code, script_code = lang.split("_")
        for i in range(len(sents)):
            sents[i] = sents[i].replace(" ", "").replace("▁", " ").strip()
            if script_code in {"Arab", "Aran"}:
                sents[i] = sents[i].replace(" ؟", "؟").replace(" ۔", "۔").replace(" ،", "،")
                sents[i] = sents[i].replace("ٮ۪", "ؠ")

        for i in range(len(sents)):
            for key in placeholder_entity_map[i].keys():
                sents[i] = sents[i].replace(key, placeholder_entity_map[i][key])

        postprocessed_sents = []
        if lang == "eng_Latn":
            for sent in sents:
                postprocessed_sents.append(self.en_detok.detokenize(sent.split(" ")))
        else:
            for sent in sents:
                outstr = indic_detokenize.trivial_detokenize(
                    self.xliterator.transliterate(sent, flores_codes[common_lang], flores_codes[lang]),
                    flores_codes[lang],
                )
                if lang_code == "ory":
                    outstr = outstr.replace("ଯ଼", "ୟ")
                postprocessed_sents.append(outstr)
        return postprocessed_sents
