# Conan Manager

Applicazione locale per catalogare e riprodurre una raccolta personale di episodi e film di Detective Conan.

## Funzioni

- più cartelle contemporaneamente, classificate come **Episodi** o **Film**;
- scansione automatica anche nelle sottocartelle;
- player video integrato con ripresa dall'ultimo minuto;
- filtri, ricerca, stato visto e titoli italiano, inglese e giapponese;
- modifica controllata dei nomi degli episodi;
- funzionamento esclusivamente locale su `127.0.0.1`.

## Requisiti e avvio

Servono Windows 10/11 e Python 3.10 o successivo. Non sono necessarie librerie Python esterne.

1. Scarica o clona la repository.
2. Avvia `Avvia_Conan_Manager.bat`.
3. Premi **Sfoglia…**, scegli una cartella, indica se contiene episodi o film e premi **Aggiungi cartella**.
4. Per fermare il server usa `Chiudi_Conan_Manager.bat`.

In alternativa esegui `python server.py`. Il sito viene aperto su <http://127.0.0.1:8765/>.

## Nomi riconosciuti

Per gli episodi è consigliato `MeitanteiConan_Ep_01_SUB_ITA.mp4`. Per i film il programma accetta qualsiasi MP4 o MOV. Se nel nome trova `Film 01` o `Movie 01`, mostra anche quel numero.

## Dati locali

Impostazioni, progressi e modifiche vengono creati nella cartella dell'applicazione e sono esclusi da Git. I video non vengono copiati nel progetto e non vengono inviati online.

Le schermate dei titoli non sono incluse: puoi conservarle localmente dentro `title_cards/` insieme al tuo `title_cards.json`.

Il server ascolta soltanto su `127.0.0.1`. Rimuovere una raccolta dal sito non elimina né sposta i video.

## Licenza

Non è stata ancora scelta una licenza. Aggiungine una prima di distribuire il progetto o accettare contributi.
