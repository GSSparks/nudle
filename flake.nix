{
  description = "reson-voice dev environment (VAD + Whisper + audio)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        python = pkgs.python311.withPackages (ps: with ps; [
          faster-whisper
          webrtcvad
          sounddevice
          numpy
          scipy
          requests
          setuptools
          pyttsx3
          uvicorn
          fastapi
          mutagen
          watchdog
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          name = "reson-voice-dev";

          packages = with pkgs; [
            python

            # Audio + STT native deps
            portaudio
            ffmpeg
            alsa-utils
            espeak-classic
            mpg123
            piper-tts

            # Utilities
            git
            curl
          ];

          shellHook = ''
            echo "🎙️ reson-voice dev shell loaded"
            echo "🐍 $(python --version)"
            echo "🧠 Whisper: tiny.en (CPU)"
            echo "🔊 Audio stack ready (ALSA + PortAudio)"

            # Use Python-only TFLite runtime for pyopen-wakeword
            export OPENWAKEWORD_USE_PYTHON_TFLITE=1
            export LD_LIBRARY_PATH=${pkgs.espeak-classic}/lib:$LD_LIBRARY_PATH
          '';
        };
      }
    );
}
