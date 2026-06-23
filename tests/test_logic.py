from main import classify_lead, choose_goal, parse_start_payload, valid_contact_value


def test_classify_lead_hot():
    lead = {
        "consent": True,
        "goal": "ВНЖ",
        "target_country": "Испания",
        "target_country_unknown": False,
        "timeline": "1–3 месяца",
        "budget": "3 000–7 000 €",
        "contact_value": "@ivanov",
    }
    assert classify_lead(lead) == "hot"


def test_classify_lead_warm_when_goal_and_contact_exist():
    lead = {
        "consent": True,
        "goal": "ВНЖ",
        "contact_value": "+49123456789",
    }
    assert classify_lead(lead) == "warm"


def test_classify_lead_cold_for_non_specific_goal():
    lead = {
        "consent": True,
        "goal": "Другое",
        "contact_value": "+49123456789",
    }
    assert classify_lead(lead) == "cold"


def test_classify_lead_stopped_without_consent():
    lead = {"consent": False, "goal": "ВНЖ", "contact_value": "@ivanov"}
    assert classify_lead(lead) == "stopped"


def test_choose_goal_accepts_synonyms():
    assert choose_goal("вид на жительство") == "ВНЖ"


def test_parse_start_payload_supports_pipe_format():
    defaults = {"entry_source": "video_01", "utm_source": "youtube", "utm_campaign": "migration_video_a"}
    parsed = parse_start_payload("video_02|telegram|migration_video_b", defaults)
    assert parsed == {"entry_source": "video_02", "utm_source": "telegram", "utm_campaign": "migration_video_b"}


def test_parse_start_payload_supports_query_format():
    defaults = {"entry_source": "video_01", "utm_source": "youtube", "utm_campaign": "migration_video_a"}
    parsed = parse_start_payload(
        "entry_source=video_03&utm_source=instagram&utm_campaign=campaign_x",
        defaults,
    )
    assert parsed == {"entry_source": "video_03", "utm_source": "instagram", "utm_campaign": "campaign_x"}


def test_valid_contact_value_email_and_phone():
    assert valid_contact_value("Email", "test@example.com") == "test@example.com"
    assert valid_contact_value("Телефон", "+49 123 456 789") == "+49 123 456 789"
    assert valid_contact_value("Telegram", "@ivanov") == "@ivanov"
