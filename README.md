# UNSW Battlecode – bot của team

## Thư mục

| Thư mục / file | Là gì |
|---|---|
| `v9/` | **Bot mạnh nhất hiện tại** = V8 + nuôi con chủ lực cuối trận. Nộp bản này |
| `v8/` | Bot V8 của team, giữ lại để so sánh |
| `smartbot/` | Bot đơn giản ban đầu (yếu hơn V8) |
| `tools/replay_stats.py` | Đọc file `.replay` và in thống kê từng team (cần Node.js) |
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

1. Copy bot hiện tại thành bản mới, ví dụ `v9` sang `v10`.
2. Chỉ sửa **một** thứ trong `v10/main.py` (một nút chỉnh hoặc một đoạn logic).
3. Chạy:
   ```
   python arena.py v10 v9 --seeds 2
   ```
4. Đọc dòng kết quả cuối:
   - `v10 MANH HON`: cận dưới của khoảng tin cậy 95% lớn hơn 50%. Giữ bản mới.
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

## V9 khác V8 ở đâu (học từ replay của các team top)

Phân tích replay cho thấy hai điều:

- Team mình thua 3 trận vì tiebreak "con dài nhất". Swarm có 30–50 con nhưng con dài nhất chỉ 7–11, còn đối thủ có con 19–28.
- Team top cho con nhỏ tự sát ngay cạnh con dài nhất từ khoảng round 340. Con dài L chết sẽ rơi ⌈L/2⌉ ngọc, và con dài nhất ăn hết. Kết quả là con dài nhất của họ tăng từ 15 lên 36.

V9 giữ nguyên V8 cho tới round 330, sau đó:

1. **Sonar**: con dài (từ 6 trở lên) phát vị trí và độ dài của nó. Con nhỏ nhận tin rồi chuyển tiếp.
2. **Nuôi**: con dài tối đa 4 bò tới cạnh đầu con dài nhất. Nếu con dài nhất không có ngọc nào trong phạm vi 3 bước, con nhỏ tự sát để rơi ngọc ngay trước mặt nó.
3. **Gộp**: từ round 400, cả những con dài vừa cũng tự sát cạnh một con dài hơn chúng ít nhất 3. Mục đích là dồn hết độ dài vào một con.
4. **Giữ ngọc**: con nhỏ không ăn ngọc nằm trong phạm vi 3 ô quanh đầu con dài nhất.
5. **Bảo vệ**: con dài từ 9 trở lên né đầu địch mạnh gấp 3 lần. Mất con chủ lực là mất tiebreak, và ngọc từ xác nó rơi cho địch ăn.
6. Giữ lại ít nhất 8 con, tức là không nuôi quá tay, cho tới round 470.

Kết quả V9 đấu V8 (sandbox, đổi bên A/B): **31 thắng, 15 thua (67%, khoảng tin cậy 95% là 53–79%)**. Riêng các map kéo dài tới round 500, V9 thắng 15/20. Các nút chỉnh nằm ở `FEED_ROUND`, `MERGE_ROUND`, `FEED_MIN_UNITS`, `KEEPER_GUARD_LEN` trong `v9/main.py`.

## Học từ replay

```
python tools/replay_stats.py M399321.replay M399314.replay
```

Lệnh này in theo thời gian: số con, con dài nhất, nguyên nhân chết (W=kelp, S=tự cắn, O=đâm thân, H=đâm đầu, A=không ra lệnh hoặc tự sát), kích thước khi split, số lần sprint và sonar, và số lần tự sát gần con dài. Cần cài Node.js.

## Nộp bài

```
unswbc auth set bc_...
unswbc submit v9 -n v9 -d "V8 + late-game feeding of the longest dragon"
```
