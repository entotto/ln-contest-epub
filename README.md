Create an EPUB file out of documents hosted on Google Drive.

## Setup

1. [Create a Google Cloud project](https://cloud.google.com/resource-manager/docs/creating-managing-projects)
1. [Enable Google Drive API](https://cloud.google.com/endpoints/docs/openapi/enable-api) for the project
1. [Create an API key](https://cloud.google.com/docs/authentication/api-keys)
1. Create a `.env` file at the root of the project and fill in the value of the API key

   ```sh
   cp sample.env .env
   vi .env
   ```

1. If you have Nix installed, run `nix-shell`.
1. If not, make sure you have access to the following:

   - Python environment with the following packages
     - doit
     - EbookLib
     - httpx
     - jinja2
     - pydantic
     - pyyaml
   - `chromium`

   and run `source .env`.

## Populating the book content

Copy `sample.yaml` as `book.yaml` and edit the entries list.

- `emoji_url`: Each entry will be accompanied by a memorable emoji. Enter the URL of an image to use.
- `emoji_name`: The name of the emoji to make it easier to reference the emoji in discussion.
- `title`: Entry title.
- `tags`: Entry tags. It could be a YAML list of strings or a comma-separated list of strings.
- `url`: URL of the Google Drive document that hosts the entry content.

## Generating the book

```sh
doit epub
```

The book file will be found at `build/book.epub`.

If a document doesn't have the option to download it enabled, then the entry will only
contain a link to the original document.

## Resources
- Cover image uses texture from https://www.transparenttextures.com/
- Stylesheet courtesy of http://bbebooksthailand.com/bb-CSS-boilerplate.html
