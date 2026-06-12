from backend.services.dem_processing_service import format_srtm_tile_name, list_srtm_tiles_for_bbox


def test_format_srtm_tile_name_longitude_padded_to_three_digits():
    assert format_srtm_tile_name(28, 96) == "N28E096"
    assert format_srtm_tile_name(28, 5) == "N28E005"
    assert format_srtm_tile_name(28, 105) == "N28E105"


def test_format_srtm_tile_name_latitude_padded_to_two_digits():
    assert format_srtm_tile_name(8, 96) == "N08E096"
    assert format_srtm_tile_name(-35, -74) == "S35W074"


def test_list_srtm_tiles_for_bbox_single_tile():
    assert list_srtm_tiles_for_bbox(28, 29, 96, 97) == ["N28E096"]
