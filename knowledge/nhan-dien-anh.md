# Lưu ý nhận diện ảnh (ghép vào prompt của AI phân tích ảnh)

Nội dung dưới dòng "---" được gửi kèm cho AI mỗi lần phân tích ảnh. Viết ngắn, cụ thể, theo dạng gạch đầu dòng.
Thêm một dòng mỗi khi thấy AI nhận nhầm một trường hợp. Sửa xong: khởi động lại worker.

---

Workshop notes (Vietnamese custom furniture market):

- Sliding doors (cánh lùa): leaves overlap each other when closed, there are NO visible hinges, a metal
  track is often visible along the top or bottom edge, and a single leaf often spans more than one
  internal section. Mirror or glass leaves on wardrobes are almost always sliding. Report every sliding
  leaf as a `sliding_door` front.
- Hinged doors (cánh mở): each door sits in front of exactly one section (or two doors per section),
  with a small even gap between doors; handles are usually near the opening edge.
- Count sections by the vertical dividers you can see inside, or by the door layout when doors are closed.
  With sliding doors closed, internal sections are usually NOT visible — say so in `review_hints`.
- A top storage box (hộc trên) above a hanging space is common on wardrobes: a separate, shorter row of
  doors or an open shelf near the ceiling.
- Plinth (len chân): a recessed board at floor level. Legs (chân): visible feet with a gap under the carcass.
- Common finishes: plain white, light/natural oak, walnut, grey or anthracite melamine (MFC); painted MDF
  looks perfectly uniform and often has a slight sheen.
