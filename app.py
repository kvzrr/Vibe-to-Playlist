import os
from dotenv import load_dotenv
import gradio as gr

# Импортируем локальные модули проекта
from src.vlm_analyzer import analyze_vibe
from src.music_search import search_tracks

# Загрузка переменных окружения из .env
load_dotenv()

# Кастомные стили и тема интерфейса
CUSTOM_CSS = """
.container { max-width: 1100px; margin: 0 auto; padding-top: 20px; }
.vibe-box { font-size: 1.1em; line-height: 1.5; }
"""
theme = gr.themes.Soft()


def generate_playlist(image):
    """
    Основная функция обработки:
    1. Принимает фото
    2. Анализирует вайб через VLM/LLM
    3. Находит релевантные треки в Яндекс Музыке
    4. Возвращает описание вайба, обложки и ссылки на треки
    """
    if image is None:
        return "Пожалуйста, загрузите изображение.", [], ""

    try:
        # 1. Анализируем изображение (получаем объект VibeAnalysis)
        vibe = analyze_vibe(image)

        # Формируем текст с описанием (используем встроенный метод to_markdown или свой формат)
        genres_str = ", ".join(vibe.genres) if vibe.genres else "—"
        keywords_str = ", ".join(vibe.keywords) if vibe.keywords else "—"
        
        vibe_text = (
            f"### 🎨 Распознанная атмосфера\n\n"
            f"**Описание:** {vibe.description}\n\n"
            f"**Жанры:** {genres_str}\n\n"
            f"**Ключевые теги:** {keywords_str}"
        )

        # 2. Ищем треки в Яндекс Музыке (передаем объект vibe, распаковываем кортеж)
        tracks, error_msg = search_tracks(vibe)

        if error_msg:
            return vibe_text, [], f"❌ Ошибка Яндекс Музыки: {error_msg}"

        if not tracks:
            return vibe_text, [], "Не удалось найти подходящие треки в Яндекс Музыке."

        # Формируем список обложек для галереи: (URL картинки, Подпись)
        # Обращаемся к атрибутам dataclass через точку: track.album_art, track.artist, etc.
        gallery_items = [
            (track.album_art, f"{track.artist} — {track.name}")
            for track in tracks
            if track.album_art
        ]

        # Формируем кликабельный список ссылок
        playlist_md = "### 🎧 Плейлист в Яндекс Музыке:\n"
        for i, track in enumerate(tracks, 1):
            playlist_md += f"{i}. [{track.artist} — {track.name}]({track.url})\n"
        return vibe_text, gallery_items, playlist_md

    except Exception as e:
        return f"❌ Ошибка при обработке: {str(e)}", [], ""


def build_ui():
    """Сборка веб-интерфейса Gradio"""
    with gr.Blocks(title="Vibe-to-Playlist") as demo:
        gr.Markdown(
            """
            # 🎵 Vibe-to-Playlist Generator
            Загрузите фото (закат, интерьер, одежда, погода), чтобы ИИ считал его настроение и создал плейлист в Яндекс Музыке!
            """
        )

        with gr.Row():
            # Левая колонка: Загрузка файла и кнопка
            with gr.Column(scale=1):
                image_input = gr.Image(
                    type="pil", 
                    label="Загрузите изображение"
                )
                generate_btn = gr.Button("🔮 Сгенерировать плейлист", variant="primary")

            # Правая колонка: Вывод результатов
            with gr.Column(scale=1):
                vibe_output = gr.Markdown(label="Атмосфера")
                
                playlist_gallery = gr.Gallery(
                    label="Обложки альбомов",
                    columns=3,
                    height="auto",
                    object_fit="cover"
                )
                
                playlist_links = gr.Markdown(label="Ссылки на Яндекс Музыку")

        # Привязка функции к кнопке
        generate_btn.click(
            fn=generate_playlist,
            inputs=[image_input],
            outputs=[vibe_output, playlist_gallery, playlist_links]
        )

    return demo


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    
    build_ui().launch(
        server_name="0.0.0.0", 
        server_port=port, 
        theme=theme, 
        css=CUSTOM_CSS
    )