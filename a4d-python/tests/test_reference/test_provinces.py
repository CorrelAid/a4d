"""Tests for province validation."""

from a4d.reference import (
    get_country_for_province,
    is_valid_province,
    load_allowed_provinces,
    load_provinces_by_country,
)


class TestLoadAllowedProvinces:
    """Tests for load_allowed_provinces function."""

    def test_loads_provinces_from_yaml(self):
        """Test that provinces are loaded from YAML file."""
        provinces = load_allowed_provinces()

        assert isinstance(provinces, list)
        assert len(provinces) > 0
        assert all(isinstance(p, str) for p in provinces)

    def test_provinces_are_lowercased(self):
        """Test that all provinces are lowercased for case-insensitive matching."""
        provinces = load_allowed_provinces()

        # All should be lowercase
        assert all(p == p.lower() for p in provinces)

    def test_includes_known_provinces_lowercased(self):
        """Test that known provinces are included (lowercased)."""
        provinces = load_allowed_provinces()

        # Test samples from each country in the YAML (lowercased)
        assert "bangkok" in provinces  # Thailand
        assert "vientiane" in provinces  # Laos
        assert "hà nội*" in provinces  # Vietnam (note the asterisk)
        assert "phnom penh" in provinces  # Cambodia
        assert "yangon region" in provinces  # Myanmar
        assert "kuala lumpur*" in provinces  # Malaysia

    def test_returns_flattened_list(self):
        """Test that provinces from all countries are in single list."""
        provinces = load_allowed_provinces()
        provinces_by_country = load_provinces_by_country()

        # Count should match flattened version
        expected_count = sum(len(provs) for provs in provinces_by_country.values())
        assert len(provinces) == expected_count

    def test_no_duplicates(self):
        """Test that there are no duplicate provinces in the list."""
        provinces = load_allowed_provinces()

        assert len(provinces) == len(set(provinces))


class TestLoadProvincesByCountry:
    """Tests for load_provinces_by_country function."""

    def test_loads_provinces_by_country(self):
        """Test that provinces are organized by country."""
        provinces_by_country = load_provinces_by_country()

        assert isinstance(provinces_by_country, dict)
        assert len(provinces_by_country) > 0

    def test_provinces_are_lowercased(self):
        """Test that all provinces are lowercased."""
        provinces_by_country = load_provinces_by_country()

        for country, provinces in provinces_by_country.items():
            assert all(p == p.lower() for p in provinces)

    def test_includes_expected_countries(self):
        """Test that expected countries are present."""
        provinces_by_country = load_provinces_by_country()

        expected_countries = [
            "THAILAND",
            "LAOS",
            "VIETNAM",
            "CAMBODIA",
            "MYANMAR",
            "MALAYSIA",
        ]

        for country in expected_countries:
            assert country in provinces_by_country
            assert len(provinces_by_country[country]) > 0

    def test_thailand_provinces(self):
        """Test that Thailand has correct number of provinces."""
        provinces_by_country = load_provinces_by_country()

        thailand_provinces = provinces_by_country["THAILAND"]

        # Thailand has 72 provinces in the data file
        assert len(thailand_provinces) == 72
        assert "bangkok" in thailand_provinces
        assert "chiang mai" in thailand_provinces
        assert "phuket" in thailand_provinces


class TestIsValidProvince:
    """Tests for is_valid_province function."""

    def test_valid_province_returns_true(self):
        """Test that valid provinces return True."""
        assert is_valid_province("Bangkok")
        assert is_valid_province("Vientiane")
        assert is_valid_province("Hà Nội*")
        assert is_valid_province("Phnom Penh")

    def test_invalid_province_returns_false(self):
        """Test that invalid provinces return False."""
        assert not is_valid_province("Invalid Province")
        assert not is_valid_province("Unknown City")
        assert not is_valid_province("Test")

    def test_none_returns_true(self):
        """Test that None is considered valid (nullable field)."""
        assert is_valid_province(None)

    def test_empty_string_returns_false(self):
        """Test that empty string is invalid."""
        assert not is_valid_province("")

    def test_case_insensitive(self):
        """Test that validation is case-insensitive."""
        assert is_valid_province("Bangkok")
        assert is_valid_province("bangkok")
        assert is_valid_province("BANGKOK")
        assert is_valid_province("BaNgKoK")

    def test_unicode_provinces(self):
        """Test that Unicode province names work correctly."""
        # Vietnam has many provinces with Unicode characters
        assert is_valid_province("Hà Nội*")
        assert is_valid_province("Hồ Chí Minh*")
        assert is_valid_province("Bà Rịa–Vũng Tàu")
        assert is_valid_province("Đà Nẵng*")

        # Case variations
        assert is_valid_province("HÀ NỘI*")
        assert is_valid_province("hà nội*")


class TestGetCountryForProvince:
    """Tests for get_country_for_province function."""

    def test_returns_correct_country(self):
        """Test that correct country is returned for provinces."""
        assert get_country_for_province("Bangkok") == "THAILAND"
        assert get_country_for_province("Vientiane") == "LAOS"
        assert get_country_for_province("Hà Nội*") == "VIETNAM"
        assert get_country_for_province("Phnom Penh") == "CAMBODIA"
        assert get_country_for_province("Yangon Region") == "MYANMAR"
        assert get_country_for_province("Kuala Lumpur*") == "MALAYSIA"

    def test_returns_none_for_invalid_province(self):
        """Test that None is returned for invalid provinces."""
        assert get_country_for_province("Invalid Province") is None
        assert get_country_for_province("Unknown") is None

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        assert get_country_for_province("Bangkok") == "THAILAND"
        assert get_country_for_province("bangkok") == "THAILAND"
        assert get_country_for_province("BANGKOK") == "THAILAND"
        assert get_country_for_province("BaNgKoK") == "THAILAND"

    def test_multiple_provinces_same_country(self):
        """Test that different provinces from same country work."""
        # All should return THAILAND
        assert get_country_for_province("Bangkok") == "THAILAND"
        assert get_country_for_province("Chiang Mai") == "THAILAND"
        assert get_country_for_province("Phuket") == "THAILAND"

    def test_unicode_provinces(self):
        """Test that Unicode provinces work correctly."""
        assert get_country_for_province("Hà Nội*") == "VIETNAM"
        assert get_country_for_province("hà nội*") == "VIETNAM"
        assert get_country_for_province("HÀ NỘI*") == "VIETNAM"


class TestIntegrationWithActualData:
    """Integration tests with actual reference_data file."""

    def test_all_countries_have_provinces(self):
        """Test that every country has at least one province."""
        provinces_by_country = load_provinces_by_country()

        for country, provinces in provinces_by_country.items():
            assert len(provinces) > 0, f"{country} has no provinces"

    def test_total_province_count(self):
        """Test that total province count is reasonable."""
        provinces = load_allowed_provinces()

        # We expect 200+ provinces across all countries
        assert len(provinces) > 200

    def test_no_empty_province_names(self):
        """Test that no province names are empty strings."""
        provinces = load_allowed_provinces()

        assert all(p.strip() for p in provinces)

    def test_round_trip_validation(self):
        """Test that all loaded provinces pass validation."""
        provinces = load_allowed_provinces()

        for province in provinces:
            assert is_valid_province(province)
            country = get_country_for_province(province)
            assert country is not None

    def test_special_characters_preserved(self):
        """Test that special characters in province names are preserved."""
        provinces = load_allowed_provinces()

        # Vietnam provinces with Unicode (lowercased)
        unicode_provinces = [p for p in provinces if any(ord(c) > 127 for c in p)]
        assert len(unicode_provinces) > 0

        # Provinces with asterisks (indicating cities, lowercased)
        asterisk_provinces = [p for p in provinces if "*" in p]
        assert len(asterisk_provinces) > 0

    def test_case_insensitive_validation_comprehensive(self):
        """Test case-insensitive validation with various cases."""
        provinces_by_country = load_provinces_by_country()

        # Get a few provinces from the data
        thailand = provinces_by_country["THAILAND"]
        vietnam = provinces_by_country["VIETNAM"]

        # Test that both original case and variations work
        # (provinces are stored lowercase, so we test against "bangkok")
        assert is_valid_province("Bangkok")  # Title case
        assert is_valid_province("BANGKOK")  # Upper case
        assert is_valid_province("bangkok")  # Lower case

        # Test with Vietnamese provinces
        test_province = vietnam[0]  # Get first province
        assert is_valid_province(test_province)
        assert is_valid_province(test_province.upper())
        assert is_valid_province(test_province.title())
