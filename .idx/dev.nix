{ pkgs, ... }: {
  channel = "unstable";
  packages = [
    pkgs.python313
    pkgs.python313Packages.pip
    pkgs.uv
  ];
  idx.previews = {};
}