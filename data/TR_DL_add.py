import fileinput

# 使用 fileinput 對原始文件進行逐行處理並直接修改
with fileinput.FileInput('train.source', inplace=True, backup='.bak') as file:
    for line in file:
        # 刪除行尾的換行符
        line = line.rstrip('\n')

        # 在行末添加 "TL;DR:" 字符串
        modified_line = line + " TL;DR:"

        # 輸出修改後的行
        print(modified_line)

# 刪除副本文件
fileinput.close()
