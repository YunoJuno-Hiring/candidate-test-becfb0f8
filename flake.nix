{
  description = "YunoJuno take-home — development environment";

  inputs = {
    # Pin via flake.lock; bump with `nix flake update`.
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Python toolchain — matches the backend stack (Django 5.x on Python 3.14)
            python314
            uv

            # Node toolchain — nodejs-slim deliberately excludes npm.
            # We use pnpm exclusively; npm's post-install script behaviour
            # is considered a security risk on this project.
            nodejs-slim_24
            pnpm

            # Utilities
            go-task
          ];

          shellHook = ''
            echo ""
            echo "YunoJuno take-home dev shell"
            echo "  Python: $(python --version 2>&1)"
            echo "  uv:     $(uv --version 2>&1)"
            echo "  Node:   $(node --version 2>&1)"
            echo "  pnpm:   $(pnpm --version 2>&1)"
            echo ""
          '';
        };
      });
}
