# hola website

Static pitch website for hola. Edit the HTML, CSS and JavaScript directly in `dist/`; there is no build step.

## Preview locally

From this directory:

```sh
python3 -m http.server 8080 --directory dist
```

Open http://localhost:8080 in your browser.

## Files

- `dist/index.html`: slides and navigation
- `dist/style.css`: styling
- `dist/*.js`: navigation and animations
- `dist/assets/`: images
- `dist/data-sources.json`: metric sources and scenario assumptions
- `.openai/hosting.json`: existing Sites project and static directory configuration

Run Sites packaging from this `website/` directory. The existing hosted website is unchanged by this local move.
