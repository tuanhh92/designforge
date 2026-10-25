# Thêm loại tủ hoặc cấu kiện mới (hướng dẫn cho người và Cursor)

Làm theo đúng thứ tự này. Mẫu đã làm: cánh lùa + thanh treo (`_sliding_doors`, `HangingCompartment`).

1. **Viết hướng dẫn trước** trong `knowledge/huong-dan/<ten>.md`: cấu kiện gồm những tấm nào, kích thước tính
   thế nào, dán cạnh nào, phụ kiện gì, giới hạn nào cần kiểm tra. Con số mặc định đưa vào `knowledge/quy-cach.yaml`.
2. **Mô hình thông số** (`python/df_domain/spec.py`): thêm kiểu mới (ví dụ `DrawersCompartment` đã có sẵn).
   Giữ thông số **ngắn, người sửa được**; không đưa kích thước từng tấm vào đây.
3. **Bộ tạo chi tiết** (`python/df_parametric/carcass.py`): hàm thuần — không đọc file, không ngẫu nhiên,
   số nguyên mm, đặt `key` ổn định cho từng chi tiết, đọc quy cách qua `ctx.r("nhom.khoa", mac_dinh)`.
4. **Test trước khi xem trên web** (`python/tests/`): kích thước, số chi tiết, không va chạm
   (`world_aabb`), chạy hai lần ra cùng `graph_hash`.
5. **Quy tắc kiểm tra** (`apps/api/src/df_services/spec_generator.py` → `validate_spec`): mã lỗi viết HOA,
   kèm `params` để dịch, và gợi ý sửa (JSON Patch) nếu có.
6. **AI** (`build_spec` + `knowledge/nhan-dien-anh.md`): khi nào AI chọn cấu kiện này.
7. **SketchUp**: vai trò mới cần gắn đúng nhóm (tag) trong `TAG_BY_ROLE` (`python/df_geometry/engine.py`).
8. **Web**: trình chỉnh sửa (`apps/web/components/spec-panel.tsx`), tên chi tiết và lỗi bằng tiếng Việt
   (`apps/web/lib/i18n/messages.ts` + `PART_PREFIXES`), vai trò cánh trong `model-viewer.tsx` nếu là cánh.
9. Chạy toàn bộ test, dựng một thiết kế mẫu, xem trên web (ẩn/hiện cánh, bảng chi tiết, ảnh "Bên trong").
