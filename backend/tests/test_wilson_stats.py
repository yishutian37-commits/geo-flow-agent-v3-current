from app.services.wilson_stats import determine_confidence_level


def test_same_day_sampling_keeps_high_confidence_when_other_dimensions_pass():
    level = determine_confidence_level(
        n=100,
        wilson_half_width=0.05,
        time_window_days=0.01,
        mechanism_type="B",
    )

    assert level == "high"


def test_a_type_mechanism_caps_high_confidence_to_medium():
    level = determine_confidence_level(
        n=100,
        wilson_half_width=0.05,
        time_window_days=0.01,
        mechanism_type="A",
    )

    assert level == "medium"
