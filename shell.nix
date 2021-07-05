{ pkgs ? import <nixpkgs> {}
}:
let
  ebookLib = pkgs.python3Packages.buildPythonPackage rec {
    pname = "EbookLib";
    version = "0.17.1";

    src = pkgs.python3Packages.fetchPypi {
      inherit pname version;
      sha256 = "1w972g0kmh9cdxf3kjr7v4k99wvv4lxv3rxkip39c08550nf48zy";
    };

    doCheck = false;
    propagatedBuildInputs = with pkgs.python3Packages; [ lxml six ];

    meta = with pkgs.lib; {
      homepage = "https://github.com/aerkalov/ebooklib";
      description = "Ebook library which can handle EPUB2/EPUB3 and Kindle format";
      license = licenses.agpl3;
      maintainers = with maintainers; [];
    };
  };
  readabilipy = pkgs.python3Packages.buildPythonPackage rec {
    pname = "readabilipy";
    version = "0.2.0";

    src = pkgs.python3Packages.fetchPypi {
      inherit pname version;
      sha256 = "1rfs1wjrqzqg4gxn28mc8kw8nn3nsx58c23czd120dlzn53z72q9";
    };

    doCheck = false;
    propagatedBuildInputs = with pkgs.python3Packages; [
      beautifulsoup4
      html5lib
      lxml
      regex
    ];

    meta = with pkgs.lib; {
      homepage = "https://github.com/alan-turing-institute/ReadabiliPy";
      description = "A simple HTML content extractor in Python. Can be run as a wrapper for Mozilla's Readability.js package or in pure-python mode.";
      license = licenses.mit;
      maintainers = with maintainers; [];
    };
  };
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    chromium
    epubcheck
    #nodejs # Needed for readabilipy
    (python3.withPackages (ps: with ps; [
      doit
      ebookLib
      httpx
      jinja2
      pydantic
      pyyaml
      #readabilipy # Not using readability transformer for now
    ]))
  ];
  shellHook = ''
  if [ -f .env ]; then
    source .env
  fi
  '';
}
