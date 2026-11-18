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

            # Native deps for audio + ML
            portaudio
            libffi
            ffmpeg
            alsa-utils
            espeak-classic
            mpg123
            piper-tts

            # CUDA userspace libs (needed for torch wheels)
            #cudaPackages.cudatoolkit
            #cudaPackages.cudnn

            # Utilities
            git
            curl
            pkg-config
          ];

          shellHook = ''
            echo "🎙️ Nüdle-voice dev shell loaded"
            echo "🐍 $(python --version)"

            # Wake word config
            export OPENWAKEWORD_USE_PYTHON_TFLITE=1

            # Native libs
            export LD_LIBRARY_PATH=${pkgs.portaudio}/lib:${pkgs.libffi}/lib:${pkgs.espeak-classic}/lib:$LD_LIBRARY_PATH

            # Auto-create venv if missing
            if [ ! -d .venv ]; then
              echo "📦 Creating Python venv"
              python -m venv .venv
            fi

            source .venv/bin/activate
            echo "✅ venv activated: $(which python)"
          '';
        };
      }
    );
}
