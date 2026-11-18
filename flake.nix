{
  description = "Nüdle dev environment (VAD + Whisper + audio)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          name = "nudle-voice-dev";

          packages = with pkgs; [
            # Python (bare, venv-friendly)
            python311
            python311Packages.pip
            python311Packages.virtualenv
            python311Packages.setuptools
            python311Packages.wheel

            # Native audio + ML deps
            portaudio        # sounddevice microphone I/O
            libsndfile       # soundfile Python package
            libffi
            ffmpeg
            pipewire         # ALSA plugin so all audio routes through PipeWire
            alsa-utils       # provides aplay (used by Piper TTS output)
            espeak-classic   # TTS fallback binary
            mpg123           # alarm sound playback
            mpv              # music + radio stream playback
            piper-tts        # neural TTS binary

            # Build / utilities
            pkg-config
            git
            curl
          ];

          # Set library path before the shell hook runs so Python wheels
          # find native libs (portaudio, libsndfile, etc.) via ctypes.
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.portaudio
            pkgs.libsndfile
            pkgs.libffi
            pkgs.espeak-classic
            pkgs.zlib
            pkgs.stdenv.cc.cc.lib  # libstdc++ for torch / torchaudio wheels
          ];

          # Point ALSA at the PipeWire plugin so mic/speaker use system routing.
          # This silences the "cannot open pipewire.so" errors and lets sounddevice
          # + aplay honour whatever input/output you have selected in PipeWire.
          ALSA_PLUGIN_DIR = "${pkgs.pipewire}/lib/alsa-lib";

          shellHook = ''
            echo "🎙️  Nüdle dev shell"
            echo "🐍 $(python3 --version)"

            # Wake word backend
            export OPENWAKEWORD_USE_PYTHON_TFLITE=1

            # Pin to the Nix piper binary so the venv's Python piper-tts package
            # doesn't shadow it (the Python one requires numpy/onnxruntime and
            # has native lib issues inside the venv).
            export PIPER_BIN="${pkgs.piper-tts}/bin/piper"

            # ── venv ──────────────────────────────────────────────────────────
            if [ ! -d .venv ]; then
              echo "📦 Creating Python venv..."
              python3 -m venv .venv
            fi
            source .venv/bin/activate

            # Auto-install pip deps whenever requirements.txt changes
            REQ_HASH=$(md5sum nudle/requirements.txt | cut -d' ' -f1)
            REQ_HASH_FILE=".venv/requirements.hash"
            if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat "$REQ_HASH_FILE")" != "$REQ_HASH" ]; then
              echo "📦 Installing Python dependencies (this may take a while)..."
              pip install --quiet -r nudle/requirements.txt \
                && echo "$REQ_HASH" > "$REQ_HASH_FILE" \
                && echo "✅ Dependencies installed"
            fi

            echo "✅ venv: $(which python)"

            # ── runtime model checks ──────────────────────────────────────────
            MISSING=0
            if [ ! -f "nudle/models/pyannote_embedding/pytorch_model.bin" ]; then
              echo "⚠️  Missing speaker model: nudle/models/pyannote_embedding/pytorch_model.bin"
              MISSING=1
            fi
            if [ ! -f "nudle/tts/voices/en_US-lessac-medium.onnx" ]; then
              echo "⚠️  Missing TTS voice: nudle/tts/voices/en_US-lessac-medium.onnx"
              MISSING=1
            fi
            [ "$MISSING" -eq 0 ] && echo "✅ All model files present"

            # ── music backend ─────────────────────────────────────────────────
            _nudle_backend_start() {
              (cd nudle && uvicorn audio.backend:app \
                --host 0.0.0.0 --port 8000 --log-level warning) &
              echo $! > .nudle-backend.pid
              echo "🎵 Music backend started (PID $!)"
            }

            if [ -f .nudle-backend.pid ] && kill -0 "$(cat .nudle-backend.pid)" 2>/dev/null; then
              echo "🎵 Music backend already running (PID $(cat .nudle-backend.pid))"
            else
              _nudle_backend_start
            fi

            # Restart helper available in the shell
            nudle-backend() {
              if [ -f .nudle-backend.pid ]; then
                kill "$(cat .nudle-backend.pid)" 2>/dev/null
                rm -f .nudle-backend.pid
              fi
              _nudle_backend_start
            }

            # Stop backend when the dev shell exits
            trap '
              if [ -f .nudle-backend.pid ]; then
                kill "$(cat .nudle-backend.pid)" 2>/dev/null && echo "🛑 Music backend stopped"
                rm -f .nudle-backend.pid
              fi
            ' EXIT

            echo ""
            echo "  python nudle/main.py   — start the voice assistant"
            echo "  nudle-backend          — restart the music backend"
            echo ""
          '';
        };
      }
    );
}
