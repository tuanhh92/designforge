# Bảng câu hỏi quy cách xưởng

Điền câu trả lời vào cột **Xưởng tôi**, rồi chép con số vào [quy-cach.yaml](quy-cach.yaml) theo cột **Khoá**.
Cột **Đang dùng** là giá trị mặc định hiện tại — nếu xưởng làm giống vậy thì để nguyên.

## Ván và chỉ

| # | Câu hỏi | Khoá trong quy-cach.yaml | Đang dùng | Xưởng tôi |
|---|---|---|---|---|
| 1 | Ván thùng dày bao nhiêu? | `carcass.thickness` | 18 mm | |
| 2 | Chỉ dán cạnh ở cạnh lộ dày bao nhiêu? | `edge_band.visible_thickness` | 1 mm | |
| 3 | Máy dán cạnh có phay trước không? Phay bao nhiêu mỗi cạnh? | `edge_band.premill` | 0 (không) | |
| 4 | Khổ ván xưởng mua (dài × rộng)? Tấm dài nhất cắt được? | `limits.max_panel_length` | 2750 mm | |
| 5 | Ván nào, màu nào, mua của nhà cung cấp nào? (mã nếu có) | `danh-muc.yaml` → materials | 8 mẫu | |

## Hậu tủ

| # | Câu hỏi | Khoá | Đang dùng | Xưởng tôi |
|---|---|---|---|---|
| 6 | Hậu dày bao nhiêu? (3 / 5 / 8 mm) | `back.thickness` | 8 mm | |
| 7 | Hậu lắp kiểu gì? Rãnh, bắt vít sau lưng, hay ván dày bắt vít? | (hiện chỉ hỗ trợ **rãnh**) | rãnh | |
| 8 | Rãnh hậu cách mép sau bao nhiêu? Sâu bao nhiêu? | `back.groove_inset`, `back.groove_depth` | 16 / 10 mm | |

## Đợt và cánh mở

| # | Câu hỏi | Khoá | Đang dùng | Xưởng tôi |
|---|---|---|---|---|
| 9 | Đợt di động lùi vào so với mép trước bao nhiêu? | `shelf.front_setback` | 20 mm | |
| 10 | Đợt dài tối đa bao nhiêu thì xưởng thêm vách/đỡ? | `limits.max_shelf_span_18` | 900 mm | |
| 11 | Cánh mở rộng tối đa bao nhiêu thì xưởng chia đôi? | `limits.max_door_leaf_width` | 600 mm | |
| 12 | Bản lề hãng nào, loại nào? Cách đầu cánh bao nhiêu? | `hardware.hinge`, `hinge.end_distance` | 100 mm | |

## Cánh lùa

| # | Câu hỏi | Khoá | Đang dùng | Xưởng tôi |
|---|---|---|---|---|
| 13 | Dùng bộ ray cánh lùa nào? (hãng, mã) | `hardware.sliding_track` | (mẫu) | |
| 14 | Ray + cánh chiếm bao nhiêu chiều sâu phía trước? | `sliding.track_depth` | 90 mm | |
| 15 | Ray trên cao bao nhiêu? Ray dưới cao bao nhiêu? | `sliding.top_rail_height`, `sliding.bottom_rail_height` | 45 / 10 mm | |
| 16 | Hai cánh chồng mí bao nhiêu? | `sliding.overlap` | 40 mm | |
| 17 | Cánh lùa rộng tối đa bao nhiêu thì chuyển sang 3 cánh? | `limits.max_sliding_leaf` | 1100 mm | |
| 18 | Tủ cánh lùa thường sâu bao nhiêu? | (AI tự nâng lên 650 mm nếu chưa đo) | 650 mm | |

## Tủ áo

| # | Câu hỏi | Khoá | Đang dùng | Xưởng tôi |
|---|---|---|---|---|
| 19 | Thanh treo cách đợt phía trên bao nhiêu? | `hanging.rail_from_top` | 60 mm | |
| 20 | Khoang treo áo sâu tối thiểu bao nhiêu (sau ray, trước hậu)? | `limits.min_hanging_depth` | 500 mm | |
| 21 | Hộc trên tủ áo thường cao bao nhiêu? | (mặc định khi chọn "Treo áo + hộc trên") | 400 mm | |
| 22 | Bố trí tủ áo xưởng hay làm? (vd. khoang trái treo dài, khoang phải đợt + ngăn kéo) | (ghi vào [huong-dan/tu-ao-canh-lua.md](huong-dan/tu-ao-canh-lua.md)) | | |

## Câu hỏi mở (ghi chú tự do)

- Xưởng có máy CNC không? Hãng gì? (ảnh hưởng định dạng file khoan)
- Liên kết thùng bằng gì? (minifix + chốt gỗ, vít confirmat, chốt gỗ + keo…)
- Những lỗi xưởng hay gặp khi làm tủ từ ảnh khách gửi?
