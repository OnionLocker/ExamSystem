import datetime as dt
import unittest

from verbal_vocab import assign_vocab, brief_for, target_kinds, vocab_issues


def entry(word, kind, age, explanation="释义"):
    return {"word": word, "kind": kind, "age": age, "explanation": explanation,
            "usage": "", "trap": "", "rivals": ["近义"], "collocations": []}


BANK = [entry("旧词", "word", 20), entry("新词", "word", 0, "接续已有的事"), entry("老话", "idiom", 3)]


class VocabPick(unittest.TestCase):
    def slot(self, tag):
        return {"tag": tag, "count": 1, "kaofa_variant_name": ""}

    def test_kinds_follow_the_fill_family(self):
        self.assertEqual(target_kinds("言语理解与表达-逻辑填空-词的辨析-@collocation-object"), {"word"})
        self.assertEqual(target_kinds("言语理解与表达-逻辑填空-成语实词综合"), {"idiom"})
        self.assertEqual(target_kinds("言语理解与表达-片段阅读-中心理解题-@turning-point"), set())

    def test_newer_unused_word_is_picked_and_same_seed_stays_put(self):
        first = [self.slot("言语理解与表达-逻辑填空-词的辨析-@collocation-object")]
        assign_vocab(first, seed="batch-a", bank=BANK, recent_texts=[], today=dt.date(2026, 10, 24))
        second = [self.slot("言语理解与表达-逻辑填空-词的辨析-@collocation-object")]
        assign_vocab(second, seed="batch-a", bank=BANK, recent_texts=[], today=dt.date(2026, 10, 24))
        self.assertEqual(first[0]["vocab_word"], "新词")
        self.assertEqual(second[0]["vocab_word"], "新词")
        self.assertIn("新词", first[0]["vocab_brief"])
        used = [self.slot("言语理解与表达-逻辑填空-词的辨析-@collocation-object")]
        assign_vocab(used, seed="batch-a", bank=BANK, recent_texts=["前文已经写过新词"], today=dt.date(2026, 10, 24))
        self.assertEqual(used[0]["vocab_word"], "旧词")

    def test_idiom_slot_does_not_take_a_content_word(self):
        slots = [self.slot("言语理解与表达-逻辑填空-成语实词综合")]
        assign_vocab(slots, seed="batch-b", bank=BANK, recent_texts=[])
        self.assertEqual(slots[0]["vocab_word"], "老话")

    def test_existing_word_is_not_replaced(self):
        slots = [self.slot("言语理解与表达-逻辑填空-词的辨析-@collocation-object")]
        slots[0]["vocab_word"] = "锁定"
        slots[0]["vocab_brief"] = "指定词：锁定"
        assign_vocab(slots, seed="batch-c", bank=BANK, recent_texts=[])
        self.assertEqual(slots[0]["vocab_word"], "锁定")

    def test_correct_option_must_use_the_word_and_stem_must_not(self):
        slot = {"vocab_word": "新词"}
        options = [{"key": key, "text": text} for key, text in zip("ABCD", ["新词未断", "中止", "放弃", "停止"])]
        good = {"stem": "传统技艺在年轻人手中____。", "answer": "A", "options": options}
        self.assertEqual(vocab_issues(good, slot), [])
        leaked = {**good, "stem": "传统技艺靠新词接上。"}
        self.assertTrue(vocab_issues(leaked, slot))
        missed = {**good, "options": [{"key": "A", "text": "延续"}, *options[1:]]}
        self.assertTrue(vocab_issues(missed, slot))
        self.assertIn("新词", brief_for(BANK[1]))


if __name__ == "__main__":
    unittest.main()
