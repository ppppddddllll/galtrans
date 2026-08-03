# 测试用 Ren'Py 脚本
define sakura = Character("桜", color="#ff8888")

label start:
    scene bg classroom with fade

    "今日はいい天気だな。"

    sakura "おはようございます、主人公さん！"

    "主人公" "お、おはよう…"

    menu:
        "どうする？"
        "学校に行く":
            jump school
        "家に帰る":
            jump home

label school:
    play music "bgm.ogg"
    "学校に着いた。"
    return
