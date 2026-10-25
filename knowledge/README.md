# Kiến thức xưởng (knowledge)

Thư mục này là **nơi duy nhất** ghi lại cách xưởng làm tủ. Một nguồn, ba nơi dùng:

| File / thư mục | Ai đọc | Dùng để làm gì |
|---|---|---|
| [quy-cach.yaml](quy-cach.yaml) | **DesignForge** (lúc chạy) | Các con số: độ dày ván, ray cánh lùa, chồng mí, khe hở, giới hạn kiểm tra |
| [danh-muc.yaml](danh-muc.yaml) | **DesignForge** (lúc chạy) | Ván, nhôm, phụ kiện xưởng có. AI chỉ được chọn trong danh sách này |
| [nhan-dien-anh.md](nhan-dien-anh.md) | **AI phân tích ảnh** (ghép vào prompt) | Lưu ý để nhận diện đúng: cánh lùa hay cánh mở, đếm khoang, các trường hợp dễ nhầm |
| [huong-dan/](huong-dan/) | **Người** và **Cursor** (khi viết code) | Giải thích vì sao xưởng làm như vậy, cách dựng từng loại tủ |
| [mau/](mau/) | **Người** (kiểm tra độ chính xác AI) | Tủ xưởng đã làm: ảnh + kích thước thật |
| [cau-hoi-xuong.md](cau-hoi-xuong.md) | **Bạn** | Bảng câu hỏi để điền số liệu thật của xưởng vào `quy-cach.yaml` |

## Quy trình cập nhật

1. Trả lời [cau-hoi-xuong.md](cau-hoi-xuong.md), chép số vào [quy-cach.yaml](quy-cach.yaml) và tăng `version`.
2. Thay danh sách mẫu trong [danh-muc.yaml](danh-muc.yaml) bằng ván và phụ kiện xưởng mua.
3. Khởi động lại API và worker. Thiết kế mới dùng quy cách mới; thiết kế cũ bấm **Dựng lại mô hình** để áp dụng.
4. Mỗi lần làm xong một tủ thật, thêm một mẫu vào [mau/](mau/).

## Nguyên tắc

- **Con số thì vào YAML, lời giải thích thì vào Markdown.** Hệ thống chỉ tính toán bằng số trong YAML;
  AI không bao giờ tự "đoán" kích thước sản xuất từ lời văn.
- **Không đổi tên khoá** trong YAML (tên bên trái dấu `:`) — đó là tên code đang dùng. Chỉ sửa giá trị.
- **Không đổi `code`** của vật tư đã dùng trong thiết kế cũ; ngừng dùng thì thêm `active: false`.
- Muốn thêm một loại tủ hoặc cấu kiện mới (ngăn kéo, tủ bếp…): viết hướng dẫn vào `huong-dan/`, rồi nhờ
  Cursor/Claude làm theo [huong-dan/them-loai-tu-moi.md](huong-dan/them-loai-tu-moi.md).

Có thể dùng thư mục khác bằng biến môi trường `DF_KNOWLEDGE_DIR`.
