from __future__ import annotations

from PIL import Image

from sdga.validate import (
    GateContext,
    GateResult,
    evaluate,
    failed,
    seam_ratio,
    severity,
)
from sdga.validate.gates import (
    alpha_required,
    binary_alpha,
    dimensions_exact,
    grid_divisible,
    max_unique_colors,
    palette_conformance,
    seamless_tile,
)

PALETTE = ((0, 0, 0), (255, 255, 255))


def _checker(size: tuple[int, int] = (32, 32)) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size)
    image.putdata(
        [
            (0, 0, 0, 255) if (x + y) % 2 == 0 else (255, 255, 255, 255)
            for y in range(height)
            for x in range(width)
        ]
    )
    return image


def test_dimensions_exact_reports_the_measurement():
    result = dimensions_exact(_checker(), GateContext(size=(32, 32)))
    assert result.status == "pass"
    assert result.value == [32, 32]


def test_dimensions_exact_fails_with_both_sizes_visible():
    result = dimensions_exact(_checker((33, 32)), GateContext(size=(32, 32)))
    assert result.status == "fail"
    assert result.value == [33, 32]
    assert result.threshold == [32, 32]


def test_grid_divisible():
    assert (
        grid_divisible(_checker((33, 32)), GateContext(size=(33, 32), quantum=32)).status == "fail"
    )
    assert (
        grid_divisible(_checker((64, 32)), GateContext(size=(64, 32), quantum=32)).status == "pass"
    )


def test_palette_conformance_counts_off_palette_pixels():
    image = Image.new("RGBA", (2, 1))
    image.putdata([(0, 0, 0, 255), (10, 20, 30, 255)])
    result = palette_conformance(image, GateContext(size=(2, 1), palette=PALETTE))
    assert result.status == "fail"
    assert result.value == 1


def test_palette_conformance_passes_on_a_snapped_image():
    assert (
        palette_conformance(_checker(), GateContext(size=(32, 32), palette=PALETTE)).status
        == "pass"
    )


def test_palette_conformance_skips_when_no_palette_is_configured():
    result = palette_conformance(_checker(), GateContext(size=(32, 32)))
    assert result.status == "skipped"


def test_transparent_pixels_do_not_count_as_colours():
    image = Image.new("RGBA", (2, 1))
    image.putdata([(0, 0, 0, 0), (9, 9, 9, 0)])
    assert max_unique_colors(image, GateContext(size=(2, 1))).value == 0


def test_max_unique_colors_uses_the_configured_threshold():
    assert (
        max_unique_colors(
            _checker(), GateContext(size=(32, 32), thresholds={"max_unique_colors": 1})
        ).status
        == "fail"
    )
    assert (
        max_unique_colors(
            _checker(), GateContext(size=(32, 32), thresholds={"max_unique_colors": 2})
        ).status
        == "pass"
    )


def test_alpha_is_only_required_where_a_kind_asks_for_it():
    assert alpha_required(Image.new("RGB", (2, 2)), GateContext(size=(2, 2))).status == "fail"
    assert alpha_required(_checker(), GateContext(size=(32, 32))).status == "pass"


def test_binary_alpha_flags_partial_transparency():
    partial = Image.new("RGBA", (1, 1), (0, 0, 0, 128))
    assert binary_alpha(partial, GateContext(size=(1, 1))).status == "fail"
    assert binary_alpha(_checker(), GateContext(size=(32, 32))).status == "pass"
    assert binary_alpha(Image.new("RGB", (1, 1)), GateContext(size=(1, 1))).status == "skipped"


def test_seam_ratio_of_a_periodic_pattern_is_about_one():
    assert 0.8 <= seam_ratio(_checker()) <= 1.2


def test_seam_ratio_catches_a_discontinuous_wrap():
    image = Image.new("RGB", (32, 32))
    image.putdata([(0, 0, 0) if x < 16 else (255, 255, 255) for y in range(32) for x in range(32)])
    assert seam_ratio(image) > 1.5


def test_a_flat_tile_is_seamless_by_definition():
    flat = Image.new("RGB", (32, 32), (10, 10, 10))
    assert seam_ratio(flat) == 0.0


def test_seamless_gate_reports_value_and_threshold():
    result = seamless_tile(
        _checker(), GateContext(size=(32, 32), thresholds={"seam_edge_ratio": 1.5})
    )
    assert result.status == "pass"
    assert result.threshold == 1.5
    assert result.value <= 1.5


def test_evaluate_runs_only_the_named_gates():
    results = evaluate(["dimensions_exact"], _checker(), GateContext(size=(32, 32)))
    assert [result.gate for result in results] == ["dimensions_exact"]


def test_severity_defaults_to_error_and_honours_off():
    assert severity("seamless_tile", {}) == "error"
    assert severity("seamless_tile", {"seamless_tile": "warn"}) == "warn"
    assert severity("seamless_tile", {"seamless_tile": "off"}) == "off"
    assert severity("seamless_tile", {"seamless_tile": "nonsense"}) == "error"


def test_failed_ignores_warnings():
    results = [GateResult("seamless_tile", "fail", value=4.0)]
    assert failed(results, {}) != []
    assert failed(results, {"seamless_tile": "warn"}) == []


def test_results_serialise_without_none_noise():
    result = GateResult("grid_divisible", "pass", value=[0, 0], threshold=32)
    assert result.to_dict() == {
        "gate": "grid_divisible",
        "status": "pass",
        "value": [0, 0],
        "threshold": 32,
    }
