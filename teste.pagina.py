from pathlib import Path
from datetime import datetime
import time
import queue
import pydub
import pyaudio
from dash import html, dcc, Input, Output, State
from dash import Dash
import dash
import openai
from dotenv import find_dotenv, load_dotenv
import base64
import dash_bootstrap_components as dbc

PASTA_ARQUIVOS = Path(__file__).parent / 'arquivos'
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

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

def salva_arquivo(caminho_arquivo, conteudo):
    with open(caminho_arquivo, 'w') as f:
        f.write(conteudo)

def ler_arquivo(caminho_arquivo):
    if caminho_arquivo.exists():
        with open(caminho_arquivo) as f:
            return f.read()
    else:
        return ''

def listar_reunioes():
    listar_reunioes = PASTA_ARQUIVOS.glob('*')
    listar_reunioes = list(listar_reunioes)
    listar_reunioes.sort(reverse=True)
    reunioes_dict = {}
    for reuniao in listar_reunioes:
        data_reuniao = reuniao.stem
        ano, mes, dia, hora, min, seg = data_reuniao.split('_')
        reunioes_dict[data_reuniao] = f'{ano}/{mes}/{dia} {hora}:{min}:{seg}'
        titulo = ler_arquivo(reuniao / 'titulo.txt')
        if titulo != '':
            reunioes_dict[data_reuniao] += f' - {titulo}'
    return reunioes_dict

def transcrever_audio(caminho_audio, language='pt', response_format='text'):
    with open(caminho_audio, 'rb') as arquivo_audio:
        transcricao = openai.Transcription.create(
            model='whisper-1',
            language=language,
            response_format=response_format,
            file=arquivo_audio
        )
    return transcricao['text']

def chat_openai(mensagem, modelo='gpt-3.5-turbo-0125'):
    mensagens = [{'role': 'user', 'content': mensagem}]
    resposta = openai.ChatCompletion.create(
        model=modelo,
        messages=mensagens
    )
    return resposta['choices'][0]['message']['content']

def adiciona_audio(frames_de_audio, audio):
    for frame in frames_de_audio:
        sound = pydub.AudioSegment(
            data=frame.to_ndarray().tobytes(),
            sample_width=frame.format.bytes,
            frame_rate=frame.sample_rate,
            channels=len(frame.layout.channels),
        )
        audio += sound
    return audio

def gerar_resumo(pasta_reuniao, transcricao):
    resumo = chat_openai(mensagem=PROMPT.format(transcricao))
    salva_arquivo(pasta_reuniao / 'resumo.txt', resumo)


app.layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    html.H1("Bem-vindo ao Ata de Reunião IA 🎙️", className="header"),
    dcc.Store(id='store-page'),
    dbc.Row([
        dbc.Col([
            html.Div([
                html.Img(src="https://s3-symbol-logo.tradingview.com/neoenergia--600.png", className="sidebar-logo"),
                dcc.Dropdown(
                    id='sidebar-select',
                    options=[
                        {'label': 'Gravar Reunião', 'value': 'Gravar Reunião'},
                        {'label': 'Verificar Transcrições salvas', 'value': 'Verificar Transcrições salvas'}
                    ],
                    value='Gravar Reunião',
                    style={'color': 'black'}
                )
            ], className="sidebar-container")
        ], width=3),
        dbc.Col([
            dcc.ConfirmDialog(
                id='confirmacao-gravacao',
                message="Deseja realmente começar a gravar?",
                displayed=False
            ),
            dcc.ConfirmDialog(
                id='confirmacao-resumo',
                message="Deseja gerar um resumo para a reunião selecionada?",
                displayed=False
            ),
            dcc.ConfirmDialog(
                id='confirmacao-salvar-titulo',
                message="Deseja salvar o título da reunião?",
                displayed=False
            ),
            dcc.ConfirmDialog(
                id='confirmacao-selecao-reuniao',
                message="Deseja selecionar essa reunião?",
                displayed=False
            ),
            html.Div(id='page-content')
        ], width=9)
    ], style={'margin-top': '20px'})
])


@app.callback(
    Output('confirmacao-gravacao', 'displayed'),
    Output('confirmacao-resumo', 'displayed'),
    Output('confirmacao-salvar-titulo', 'displayed'),
    Output('confirmacao-selecao-reuniao', 'displayed'),
    Input('sidebar-select', 'value')
)
def callback_display_confirmations(value):
    return (
        value == 'Gravar Reunião',
        value == 'Verificar Transcrições salvas',
        False,
        False
    )


@app.callback(
    Output('confirmacao-resumo', 'message'),
    Input('sidebar-select', 'value')
)
def callback_message_confirmacao_resumo(value):
    return f"Você deseja gerar um resumo para a reunião selecionada?" if value == 'Verificar Transcrições salvas' else ''


@app.callback(
    Output('store-page', 'data'),
    Input('url', 'pathname')
)
def display_page(pathname):
    return pathname


@app.callback(
    Output('page-content', 'children'),
    Input('store-page', 'data'),
    prevent_initial_call=True
)
def display_page(pathname):
    if pathname == '/Gravar Reunião':
        return html.Div(tab_gravar_reuniao())
    elif pathname == '/Verificar Transcrições salvas':
        return html.Div(tab_selecao_reuniao())
    else:
        return html.Div(tab_gravar_reuniao())


def tab_gravar_reuniao():
    return html.Div([
        html.Div(id='transcricao', children=''),
        html.Button('Começar a gravar', id='button-gravar', n_clicks=0),
        dcc.Store(id='transcricao-store', data=''),
        dcc.Store(id='pasta-reuniao-store', data=''),
        dcc.Store(id='audio-store', data=pydub.AudioSegment.empty()),
        dcc.Store(id='audio-completo-store', data=pydub.AudioSegment.empty()),
        dcc.Interval(id='interval-transcricao', interval=1000),
        dcc.Interval(id='interval-pasta-reuniao', interval=1000)
    ])


app.clientside_callback(
    """
    function update_button_label(value) {
        return value ? 'Parar de gravar' : 'Começar a gravar';
    }
    """,
    Output('button-gravar', 'children'),
    Input('webr_tx', 'playing')
)


app.clientside_callback(
    """
    function trigger_confirmacao_gravacao(n_clicks) {
        if (n_clicks > 0) {
            document.getElementById('confirmacao-gravacao').click();
            return '';
        }
        return value;
    }
    """,
    Output('transcricao-store', 'data'),
    Input('button-gravar', 'n_clicks')
)


@app.callback(
    Output('transcricao', 'children'),
    Input('interval-transcricao', 'n_intervals'),
    State('transcricao-store', 'data')
)
def update_transcricao(n_intervals, transcricao):
    return transcricao


@app.callback(
    Output('pasta-reuniao-store', 'data'),
    Input('interval-pasta-reuniao', 'n_intervals'),
    State('pasta-reuniao-store', 'data')
)
def update_pasta_reuniao(n_intervals, pasta_reuniao):
    return pasta_reuniao


@app.callback(
    Output('button-gravar', 'disabled'),
    Output('confirmacao-resumo', 'displayed'),
    Input('transcricao', 'children'),
    Input('pasta-reuniao-store', 'data'),
    prevent_initial_call=True
)
def callback_gravacao_finalizada(transcricao, pasta_reuniao):
    if transcricao and pasta_reuniao:
        return False, True
    return True, False


@app.callback(
    Output('confirmacao-resumo', 'message'),
    Input('sidebar-select', 'value'),
    State('transcricao', 'children'),
    State('pasta-reuniao-store', 'data')
)
def callback_message_confirmacao_resumo(value, transcricao, pasta_reuniao):
    return f"Você deseja gerar um resumo para a reunião gravada em {pasta_reuniao}?" if value == 'Verificar Transcrições salvas' and transcricao else ''


@app.callback(
    Output('store-page', 'data'),
    Input('confirmacao-selecao-reuniao', 'submit_n_clicks'),
    State('confirmacao-selecao-reuniao', 'displayed'),
    State('pasta-reuniao-store', 'data')
)
def callback_selecao_reuniao(submit_n_clicks, displayed, pasta_reuniao):
    if submit_n_clicks and not displayed:
        return '/Verificar Transcrições salvas' if pasta_reuniao else '/'
    return '/'


@app.callback(
    Output('confirmacao-salvar-titulo', 'displayed'),
    Output('pasta-reuniao-store', 'data'),
    Input('confirmacao-selecao-reuniao', 'submit_n_clicks'),
    State('confirmacao-selecao-reuniao', 'displayed'),
    State('sidebar-select', 'value'),
    State('pasta-reuniao-store', 'data')
)
def callback_confirmacao_selecao_reuniao(submit_n_clicks, displayed, value, pasta_reuniao):
    if submit_n_clicks and not displayed:
        return True, pasta_reuniao
    return False, pasta_reuniao


@app.callback(
    Output('confirmacao-salvar-titulo', 'message'),
    Input('sidebar-select', 'value'),
    State('pasta-reuniao-store', 'data')
)
def callback_message_confirmacao_salvar_titulo(value, pasta_reuniao):
    if value == 'Verificar Transcrições salvas' and not (pasta_reuniao / 'titulo.txt').exists():
        return "A reunião selecionada não possui um título, deseja adicionar um?"
    return ''


@app.callback(
    Output('store-page', 'data'),
    Input('confirmacao-salvar-titulo', 'submit_n_clicks'),
    State('confirmacao-salvar-titulo', 'displayed'),
    State('sidebar-select', 'value'),
    State('pasta-reuniao-store', 'data')
)
def callback_salvar_titulo(submit_n_clicks, displayed, value, pasta_reuniao):
    if submit_n_clicks and not displayed:
        return '/' if value == 'Verificar Transcrições salvas' else '/'
    return '/'


@app.callback(
    Output('confirmacao-resumo', 'displayed'),
    Output('transcricao-store', 'data'),
    Input('confirmacao-resumo', 'submit_n_clicks'),
    State('confirmacao-resumo', 'displayed'),
    State('sidebar-select', 'value'),
    State('transcricao-store', 'data'),
    State('pasta-reuniao-store', 'data')
)
def callback_confirmacao_resumo(submit_n_clicks, displayed, value, transcricao, pasta_reuniao):
    if submit_n_clicks and not displayed:
        return True, transcricao + chat_openai(mensagem=PROMPT.format(transcricao)), pasta_reuniao
    return False, transcricao, pasta_reuniao


@app.callback(
    Output('button-gravar', 'n_clicks'),
    Input('confirmacao-resumo', 'submit_n_clicks'),
    State('confirmacao-resumo', 'displayed')
)
def callback_reset_button_gravar(submit_n_clicks, displayed):
    if submit_n_clicks and not displayed:
        return 0
    return dash.no_update


def tab_selecao_reuniao():
    reunioes_dict = listar_reunioes()

    if len(reunioes_dict) > 0:
        reuniao_selecionada = dcc.Dropdown(
            id='reuniao-selecionada',
            options=[
                {'label': v, 'value': k} for k, v in reunioes_dict.items()
            ],
            value=list(reunioes_dict.keys())[0],
            style={'color': 'black'}
        )
        return html.Div([
            reuniao_selecionada,
            html.Button('Selecionar Reunião', id='button-selecionar-reuniao', n_clicks=0),
            dcc.ConfirmDialog(
                id='confirmacao-selecao-reuniao',
                message="Deseja realmente selecionar essa reunião?",
                displayed=False
            )
        ])
    else:
        return html.Div('Nenhuma reunião encontrada.')


@app.callback(
    Output('button-selecionar-reuniao', 'n_clicks'),
    Input('confirmacao-selecao-reuniao', 'submit_n_clicks'),
    State('confirmacao-selecao-reuniao', 'displayed')
)
def callback_reset_button_selecionar_reuniao(submit_n_clicks, displayed):
    if submit_n_clicks and not displayed:
        return 0
    return dash.no_update


if __name__ == '__main__':
    app.run_server(debug=True)
