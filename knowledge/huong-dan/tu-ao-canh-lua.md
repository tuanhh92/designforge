# Tủ áo cánh lùa

Code: `_sliding_doors()` trong `python/df_parametric/carcass.py`. Test: `python/tests/test_sliding_hanging.py`.

## Cách dựng hiện tại

- **Một bộ cánh lùa cho cả tủ** (2 hoặc 3 cánh), nằm **bên trong** thùng, giữa hai hông.
- **Vùng ray** phía trước sâu `sliding.track_depth`. Vách, đợt, thanh treo đều lùi ra sau vùng này.
- **Ray trên** (cao `sliding.top_rail_height`) dưới nóc; **ray dưới** (cao `sliding.bottom_rail_height`) trên đáy.
  Ray dài bằng lòng thùng (rộng tủ − 2 × ván).
- **Chiều cao cánh** = khoảng giữa hai ray − 2 mm (1 mm hở trên, 1 mm hở dưới).
- **Chiều rộng cánh** = (lòng thùng + chồng mí × (số cánh − 1)) ÷ số cánh, làm tròn lên.
- **Ray đôi**: ray ngoài cách mép trước 10 mm, ray trong lùi thêm một độ dày cánh + 10 mm.
  2 cánh: cánh trái ray trong, cánh phải ray ngoài. 3 cánh: cánh giữa ray trong.
- **Chiều sâu**: nếu AI thấy cánh lùa mà chưa có kích thước đo, tủ được nâng lên 650 mm để còn ≥ 500 mm treo áo.

## Bố trí xưởng hay làm (CẦN XƯỞNG ĐIỀN)

<!-- Ví dụ: "Tủ 2 cánh lùa rộng 1600–2000: khoang trái treo dài + hộc trên 400; khoang phải 4 đợt + 2 ngăn kéo dưới". -->

- …

## Chưa làm / lưu ý

- Cánh lùa kính/gương, khung nhôm bao cánh: chưa dựng (cánh hiện là tấm ván).
- Giảm chấn cánh lùa, chặn cánh: chưa có trong danh sách phụ kiện.
- Kích thước ray theo từng hãng: cập nhật `sliding.*` theo bộ ray xưởng dùng.
