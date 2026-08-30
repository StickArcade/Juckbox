import yt_dlp

def baixar_audios(lista_links):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(lista_links)

if __name__ == "__main__":
    links = []
    
    print("Cole os links (digite 'sair' para terminar):")
    
    while True:
        link = input("> ")
        if link.lower() == "sair":
            break
        links.append(link)

    baixar_audios(links)