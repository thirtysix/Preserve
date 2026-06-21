"""Tests for placeholder mapping."""

from preserve.mapping import PlaceholderMap


class TestPlaceholderMap:
    def test_add_and_retrieve(self):
        pm = PlaceholderMap()
        placeholder = pm.add("john@example.com", "EMAIL")
        assert placeholder == "[EMAIL_1]"
        assert pm.get_original("[EMAIL_1]") == "john@example.com"
        assert pm.get_placeholder("john@example.com") == "[EMAIL_1]"

    def test_sequential_ids(self):
        pm = PlaceholderMap()
        p1 = pm.add("a@b.com", "EMAIL")
        p2 = pm.add("c@d.com", "EMAIL")
        assert p1 == "[EMAIL_1]"
        assert p2 == "[EMAIL_2]"

    def test_duplicate_reuse(self):
        pm = PlaceholderMap()
        p1 = pm.add("john@example.com", "EMAIL")
        p2 = pm.add("john@example.com", "EMAIL")
        assert p1 == p2
        assert len(pm) == 1

    def test_case_insensitive_dedup(self):
        pm = PlaceholderMap()
        p1 = pm.add("John@Example.com", "EMAIL")
        p2 = pm.add("john@example.com", "EMAIL")
        assert p1 == p2

    def test_different_types(self):
        pm = PlaceholderMap()
        p1 = pm.add("john@example.com", "EMAIL")
        p2 = pm.add("123-45-6789", "SSN")
        assert p1 == "[EMAIL_1]"
        assert p2 == "[SSN_1]"

    def test_restore(self):
        pm = PlaceholderMap()
        pm.add("john@example.com", "EMAIL")
        pm.add("123-45-6789", "SSN")
        text = "Contact [EMAIL_1], SSN is [SSN_1]"
        restored = pm.restore(text)
        assert restored == "Contact john@example.com, SSN is 123-45-6789"

    def test_restore_no_placeholders(self):
        pm = PlaceholderMap()
        text = "No placeholders here"
        assert pm.restore(text) == text

    def test_custom_format(self):
        pm = PlaceholderMap(placeholder_format="<{type}-{id}>")
        p = pm.add("test@test.com", "EMAIL")
        assert p == "<EMAIL-1>"

    def test_serialization_roundtrip(self):
        pm = PlaceholderMap()
        pm.add("john@example.com", "EMAIL")
        pm.add("123-45-6789", "SSN")

        data = pm.to_dict()
        pm2 = PlaceholderMap.from_dict(data)

        assert pm2.get_original("[EMAIL_1]") == "john@example.com"
        assert pm2.get_original("[SSN_1]") == "123-45-6789"
        assert len(pm2) == 2

    def test_entries_property(self):
        pm = PlaceholderMap()
        pm.add("a@b.com", "EMAIL")
        entries = pm.entries
        assert "[EMAIL_1]" in entries
        assert entries["[EMAIL_1]"] == "a@b.com"

    def test_len(self):
        pm = PlaceholderMap()
        assert len(pm) == 0
        pm.add("a@b.com", "EMAIL")
        assert len(pm) == 1
