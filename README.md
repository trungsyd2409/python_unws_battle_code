# UNSW Battlecode – bot của team

## Thư mục

| Thư mục / file | Là gì |
|---|---|
| `smartbot/` | Bot chính để nộp. Toàn bộ chiến thuật nằm trong `main.py` |
| `starter/` | Bot mẫu gốc, dùng làm mốc so sánh |
| `mybot/` | Bot do `unswbc init` tạo ra (giống starter) |
| `arena.py` | So sánh 2 bot trên nhiều map và seed, có đổi bên A/B |
| `render.py` | In một map ra dạng chữ để xem kelp, portal và vị trí xuất phát |
| `maps/` | 13 map có sẵn |

## Chạy nhanh

```
unswbc run maps/arena.map smartbot starter             # 1 trận, xem replay trong VS Code
unswbc run maps/default.map smartbot starter --sandbox # chạy như judge, có đo CPU
python render.py maps/dilemma.map                      # xem map
```

## Kiểm tra bot mới có mạnh hơn bot cũ không

1. Copy bot hiện tại thành bản mới, ví dụ `smartbot` sang `smartbot_v2`.
2. Chỉ sửa **một** thứ trong `smartbot_v2/main.py` (một nút chỉnh hoặc một đoạn logic).
3. Chạy:
   ```
   python arena.py smartbot_v2 smartbot --seeds 2
   ```
4. Đọc dòng kết quả cuối:
   - `smartbot_v2 MANH HON`: cận dưới của khoảng tin cậy 95% lớn hơn 50%. Giữ bản mới.
   - `Chua ket luan duoc`: chạy thêm seed (`--seeds 4`) hoặc bỏ thay đổi đó.
   - `YEU HON`: bỏ thay đổi.
5. Luôn xem dòng `CPU max/luot` và giữ nó dưới khoảng 80M. Nếu lượt nào vượt 100M thì dragon đó chết.

Các tùy chọn hữu ích:

- `--maps maps/arena.map maps/default.map`: chỉ chạy một số map (nhanh hơn).
- `--save-losses`: lưu replay các trận thua vào `replays/losses/` để xem vì sao thua.
- `--fast`: chạy không sandbox. Nhanh hơn, nhưng không giống judge về CPU.

Vì sao phải chạy nhiều trận:

- Một trận đơn lẻ có yếu tố may rủi.
- Đổi bên A/B loại bỏ lợi thế đi trước (dragon có id nhỏ đi trước).
- Chạy nhiều map loại bỏ trường hợp bot chỉ giỏi trên một kiểu map.

## Chiến thuật của smartbot (mỗi lượt)

1. **Quan sát**: ghi nhớ kelp và portal (không bao giờ đổi), ngọc, đồng hồ sinh ngọc, và lần cuối nhìn thấy mỗi ô.
2. **Snipe**: nếu team còn từ 2 dragon trở lên và thấy đầu địch trong tầm sprint, lao thẳng vào đầu địch để cả hai cùng chết. Nếu địch chỉ còn 1 dragon thì mình thắng ngay.
3. **Split**: khi đủ dài thì tách con. Có nhiều dragon thì khó bị tiêu diệt hết, và nhiều miệng ăn ngọc hơn.
4. **Thoát bẫy**: khi bị kẹt trong ngõ cụt, cắt đuôi hoặc split để phần đuôi (con mới) bò ra.
5. **Di chuyển**: chấm điểm 4 hướng theo công thức sau:
   - cộng điểm mục tiêu: ngọc gần, ngọc sắp sinh, vùng lâu chưa nhìn.
   - trừ nặng nếu hướng đó không còn đủ chỗ (dùng flood fill, có tính phần thân sẽ rút đi).
   - trừ điểm nguy hiểm khi gần đầu địch.

Các nút chỉnh nằm ở đầu `smartbot/main.py`: `SPLIT_AT`, `SPLIT_CHILD`, `MAX_UNITS`, `SPLIT_LAST_ROUND`, `SNIPE`, `SNIPE_MIN_UNITS`, `BFS_LIMIT`, `EXPLORE_W`, `BUDGET`.

## Nộp bài

```
unswbc auth set bc_...
unswbc submit smartbot -n v1 -d "snipe + split + flood fill"
```
