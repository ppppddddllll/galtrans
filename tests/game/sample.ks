;mode=debug
;KAG スクリプト
*start
[wait time=200]
今日はいい天気だな。
<#ff0000>ここは赤い文字</#>です。
[char d= 'sakura']
さくら[wait time=300]「おはようございます！」
[link target=*yes]はい[endlink] / [link target=*no]いいえ[endlink]
@set story=%1
