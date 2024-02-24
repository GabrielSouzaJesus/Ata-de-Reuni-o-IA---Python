from pathlib import Path
from datetime import datetime
import time
import queue
import pydub
from streamlit_webrtc import WebRtcMode, webrtc_streamer
import openai
from dotenv import find_dotenv, load_dotenv
import streamlit as st

PASTA_ARQUIVOS =Path(__file__).parent / 'arquivos'
PASTA_ARQUIVOS.mkdir(exist_ok=True)
PROMPT = '''
Faca um resumo do texto delimitado por ### 
o texto é a transcricao de uma reunião.
o resumo deve contar com os principais assuntos abordados.
o resumo deve ter no máximo 300 caracteres.
o resumo deve estar em texto corrido.
no final, devem ser apresentados todos acordos e combinados 
feitos na reunião no formato de bullet points

o formato final que eu desejo é:

Resumo reunião:
- escrever aqui o resumo.

Acordos da Reunião:
- acordo 1
- acordo 2
- acordo 3 
- acordo n

texto: ###{}### 
'''


_ = load_dotenv(find_dotenv())
client = openai.OpenAI()


def salva_arquivo(caminho_arquivo, conteudo):
    with open(caminho_arquivo, 'w') as f:
        f.write(conteudo)

def ler_arquivo (caminho_arquivo):
    if caminho_arquivo.exists():
        with open(caminho_arquivo) as f:
            f.write(caminho_arquivo)
    else:
        return ''

def listar_reunioes ():
    listar_reunioes = PASTA_ARQUIVOS.glob('*')
    listar_reunioes = list(listar_reunioes)
    listar_reunioes.sort(reverse=True)
    reunioes_dict = {}
    for reuniao in listar_reunioes:
        data_reuniao = reuniao.stem
        ano, mes, dia, hora, min, seg = data_reuniao.split('_')
        reunioes_dict[data_reuniao] = f'{ano}/{mes}/{dia} {hora}:{min}:{seg}'
        titulo =  ler_arquivo(reuniao / 'titulo.txt')
        if titulo != '':
            reunioes_dict[data_reuniao] += f' - {titulo}'
    return reunioes_dict

def transcrever_audio(caminho_audio,language='pt', response_format='text'):
    with open(caminho_audio, 'rb') as arquivo_audio:
        transcricao = client.audio.transcriptions.create(
            model='whisper-1',
            language=language,
            response_format=response_format,
            file=arquivo_audio
        )
    return transcricao

def chat_openai(
        mensagem,
        modelo='gpt-3.5-turbo-0125'
):
    mensagens = [{'role':'user', 'content': mensagem}]
    resposta = client.chat.completions.create(
        model=modelo,
        messages=mensagens
    )
    return resposta.choices[0].message.content

def adiciona_audio(frames_de_audio, audio):
    for frame in frames_de_audio:
        sound =pydub.AudioSegment(
            data=frame.to_ndarray().tobytes(),
            sample_width=frame.format.bytes,
            frame_rate=frame.sample_rate,
            channels=len(frame.layout.channels),
                )
        audio += sound
    return audio

def tab_gravar_reuniao():
    webr_tx = webrtc_streamer(
        key='recebe_audio',
        mode=WebRtcMode.SENDONLY,
        audio_receiver_size=1024,
        media_stream_constraints={'video': False, 'audio': True},

    )
    if not webr_tx.state.playing:
        return
    container = st.empty()
    container.markdown('Comece a falar')
    pasta_reuniao = PASTA_ARQUIVOS / datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    pasta_reuniao.mkdir()

    ultima_transcricao = time.time()
    audio_completo = pydub.AudioSegment.empty()
    audio = pydub.AudioSegment.empty()
    
    transcricao = ''

    while True:
        if webr_tx.audio_receiver:
            try:
                frames_de_audio = webr_tx.audio_receiver.get_frame(timeout=1)
            except queue.Empty:
                time.sleep(0.1)
                continue
            audio = adiciona_audio(frames_de_audio, audio)
            audio_completo = adiciona_audio(frames_de_audio, audio_completo)
            if len(audio) >0:
                audio_completo.export(pasta_reuniao / 'audio.mp3')
                agora = time.time()
                if agora - ultima_transcricao > 10:
                    ultima_transcricao = agora
                    audio.export(pasta_reuniao / 'audio_temp.mp3')
                    transcricao_audio = transcrever_audio(pasta_reuniao / 'audio_temp.mp3')
                    transcricao += transcricao_audio
                    salva_arquivo(pasta_reuniao / 'transcricao.txt', transcricao)
                    container.markdown(transcricao)
                    audio = pydub.AudioSegment.empty()
        else:
            break

def tab_selecao_reuniao ():
    reunioes_dict = listar_reunioes ()

    if len(reunioes_dict) > 0:
        reuniao_selecionada = st.selectbox('Selecione uma reunião',
                                        list(reunioes_dict.values()))
        st.divider()
        reuniao_data = [ k for k, v in reunioes_dict.items() if v == reuniao_selecionada[0]]
        pasta_reuniao = PASTA_ARQUIVOS / reuniao_data
        if not (pasta_reuniao / 'titulo.txt').exist():
            st.warning('Adicione um titulo')
            titulo_reuniao = st.text_input('Título da Reunião')
            st.button('Salvar',
                      on_click=salva_arquivo,
                      args=(pasta_reuniao,titulo_reuniao))
        else:
            titulo = ler_arquivo (pasta_reuniao / 'titulo.txt')
            transcricao = ler_arquivo (pasta_reuniao / 'transcricao.txt')
            resumo = ler_arquivo (pasta_reuniao / 'resumo.txt')
            if resumo == '':
                gerar_resumo(pasta_reuniao)
                resumo = ler_arquivo (pasta_reuniao / 'resumo.txt')
            st.markdown(f'##{titulo}')
            st.markdown(f'{resumo}')
            st.markdown(f'Transcrição: {transcricao}')
            
def salvar_titulo(pasta_reuniao, titulo):
    salva_arquivo(pasta_reuniao / 'titulo.txt', titulo)

def gerar_resumo(pasta_reuniao):
    transcricao = ler_arquivo (pasta_reuniao / 'transcricao.txt')
    resumo = chat_openai(mensagem=PROMPT.format(transcricao))
    salva_arquivo(pasta_reuniao / 'resumo.txt', resumo)


# def main():
#     st.header('Bem vindo ao Ata de Reunião IA 🎙️', divider=True)
#     tab_gravar, tab_selecao = st.tabs(['Gravar Reunião', 'Verificar Transcrições salvas'])
#     with tab_gravar:
#         tab_gravar_reuniao()
#     with tab_selecao:
#         tab_selecao_reuniao()
    
def main():

    st.set_page_config(page_title="Ata Reunião IA", page_icon="🎙️", layout="wide")
    
    header_style = """
        <style>
            body {
                background-color: #d9d9d9;  /* Altere para a cor de cinza desejada */
            }
            .header {
                width: 100%;
                padding: 1rem;
                background-color: #00b300;
                color: white;
                text-align: center;
                font-size: 2rem;
                border-bottom: 2px solid #008c00;  /* Adiciona uma borda inferior */
            }
            .sidebar-container {
                padding: 1rem;
                background-color: #d9d9d9;  /* Altere para a cor de cinza desejada */
                margin-top: 1rem;
            }
            .sidebar-logo {
                width: 100%;
                margin-bottom: 1rem;
            }
        </style>
    """
    st.markdown(header_style, unsafe_allow_html=True)
    st.markdown('<p class="header">Bem-vindo ao Ata de Reunião IA 🎙️</p>', unsafe_allow_html=True)
    sidebar_container = st.sidebar.container()
    logo_url = "https://s3-symbol-logo.tradingview.com/neoenergia--600.png"
    sidebar_container.image(logo_url, use_column_width=True, output_format="PNG")
    pagina_selecionada = sidebar_container.selectbox('Selecione uma página', ['Gravar Reunião', 'Verificar Transcrições salvas'], key="sidebar-select", format_func=lambda x: x.upper())
    if pagina_selecionada == 'Gravar Reunião':
        tab_gravar_reuniao()
    elif pagina_selecionada == 'Verificar Transcrições salvas':
        tab_selecao_reuniao()

if __name__ == "__main__":
    main()




    








