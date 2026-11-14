{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in {
      packages = forAll (pkgs: {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "splashdeck";
          version = "0.2.0";
          pyproject = true;
          src = ./.;
          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = with pkgs.python3Packages; [ pillow pygobject3 pywebview ];
          nativeBuildInputs = [ pkgs.wrapGAppsHook3 pkgs.gobject-introspection ];
          buildInputs = [ pkgs.gtk3 pkgs.webkitgtk_4_1 pkgs.glib-networking ];
          postInstall = ''
            install -Dm644 icons/splashdeck.svg $out/share/icons/hicolor/scalable/apps/splashdeck.svg
            install -Dm644 splashdeck.desktop $out/share/applications/splashdeck.desktop
            install -Dm644 60-splashdeck.rules $out/lib/udev/rules.d/60-splashdeck.rules
          '';
        };
      });
      nixosModules.default = { pkgs, ... }: {
        environment.systemPackages = [ self.packages.${pkgs.system}.default ];
        services.udev.packages = [ self.packages.${pkgs.system}.default ];
      };
    };
}
