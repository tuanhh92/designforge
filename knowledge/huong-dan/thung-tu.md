# Thùng tủ — cách DesignForge dựng (và vì sao)

Áp dụng cho mọi loại tủ tấm: tủ áo, tủ sách, tủ bếp, tủ console… Các con số nằm trong
[../quy-cach.yaml](../quy-cach.yaml); file này giải thích **cách dựng** để người và Cursor hiểu.
Code tương ứng: `python/df_parametric/carcass.py`.

## Kết cấu

- **Hông phủ nóc/đáy** (`gables_over_top`): hai hông chạy suốt chiều cao thùng; nóc và đáy nằm giữa hai hông.
  Chiều dài nóc/đáy = rộng tủ − 2 × độ dày ván.
- **Chân đế**: len chân (lùi vào 50 mm) hoặc chân tăng chỉnh. Chiều cao thùng = cao tủ − chiều cao chân đế.
- **Hậu** lắp vào rãnh trên hông, nóc, đáy (cách mép sau `back.groove_inset`, sâu `back.groove_depth`).
  Hậu lớn hơn lòng thùng mỗi bên (độ sâu rãnh − 1 mm) để ăn vào rãnh.
- **Vách ngăn** nằm giữa nóc và đáy; khoang được chia đều nếu để chiều rộng "tự động".

## Ngăn trong khoang

- Mỗi khoang là một chồng ngăn **xếp từ dưới lên**. Giữa hai ngăn có một **đợt cố định** (dày bằng ván thùng).
- Ngăn có chiều cao cố định giữ nguyên; ngăn "tự động" chia phần còn lại.
- **Đợt di động**: chia đều trong ngăn, làm tròn theo bước 32 mm của hàng lỗ chốt.
- **Thanh treo**: tâm cách mặt dưới đợt phía trên `hanging.rail_from_top`; dài = rộng khoang − 4 mm.

## Chỉ dán cạnh

- Hông, nóc, đáy, vách, đợt: dán **cạnh trước (L1)**.
- Cánh (mở hoặc lùa): dán **4 cạnh**.
- Hậu, nhôm: không dán.
- Kích thước cắt = kích thước hoàn thiện − (độ dày chỉ + phay trước) ở mỗi cạnh có dán.

## Kiểm tra tự động

Xem phần `limits` trong [../quy-cach.yaml](../quy-cach.yaml). Lỗi (đỏ) chặn việc lưu; cảnh báo (vàng) chỉ nhắc.
