import csv
from pathlib import Path

rows = [
 # model, scale, total_before,total_after, real_b,real_a, miss_b,miss_a, nc_b,nc_a, rules_b,rules_a
 ["FZK_Haus","2层住宅/7房",29,17,21,9,8,8,17,25,15,7],
 ["office_3f","3层办公/24房",57,44,36,23,21,21,14,16,14,9],
 ["Duplex_MEP","MEP专项/425管",625,338,475,188,150,150,30,36,16,10],
 ["Schependomlaan","6层住宅/100房",495,213,315,33,180,180,22,31,18,7],
 ["HITOS","7层大型公建/243房",757,418,477,138,280,280,14,22,21,10],
 ["Smiley-West","5层办公/140房",267,200,167,100,100,100,17,26,13,4],
]
header = ["模型","类型/规模",
          "总问题_更新前","总问题_更新后",
          "真实违规_更新前","真实违规_更新后",
          "Missing缺字段_更新前","Missing缺字段_更新后",
          "未检查规则_更新前","未检查规则_更新后",
          "涉及规则数_更新前","涉及规则数_更新后"]

dest = Path(__file__).with_name("系统更新前后对比_2026-10-06.csv")
with open(dest,"w",newline="",encoding="utf-8-sig") as f:
    w=csv.writer(f); w.writerow(header); w.writerows(rows)
print("WROTE",dest)
