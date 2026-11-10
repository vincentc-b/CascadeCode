import com.google.gson.GsonBuilder;
import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

/** Captures trusted live-cell metadata before the pinned renderer serializes SVG. */
public final class RendererBindingAdapter {
    private static final String CAPTURE = """
        () => Array.from(document.querySelectorAll('#diagram .joint-cell')).flatMap(node => {
            node.dispatchEvent(new MouseEvent('mouseover', {
                bubbles: true,
                clientX: 1,
                clientY: 1
            }));

            let kind = null;
            let modelId = null;
            if (structurizr.diagram.hasElementHighlighted()) {
                kind = 'element';
                modelId = structurizr.diagram.getHighlightedElementId();
            } else if (structurizr.diagram.hasLinkHighlighted()) {
                kind = 'relationship';
                modelId = structurizr.diagram.getHighlightedRelationshipId();
            }

            node.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }));
            if (kind === null || modelId === undefined || modelId === null) {
                return [];
            }
            node.setAttribute('data-cascade-model-kind', kind);
            node.setAttribute('data-cascade-export-id', modelId);
            return [{
                rendererNodeId: node.id,
                kind: kind,
                modelId: modelId
            }];
        })
        """;

    private RendererBindingAdapter() {
    }

    public static void main(String[] args) throws Exception {
        Path staticSite = Path.of(args[0]).toAbsolutePath();
        Path bindingsPath = Path.of(args[1]);
        Path svgPath = Path.of(args[2]);
        String viewKey = args[3];

        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                new BrowserType.LaunchOptions()
                    .setExecutablePath(
                        Path.of("/ms-playwright/chromium-1243/chrome-linux64/chrome")
                    )
                    .setHeadless(true)
                    .setArgs(List.of("--no-sandbox"))
            );
            Page page = browser.newPage();
            page.navigate(staticSite.resolve("index.html").toUri() + "?diagram=" + viewKey);
            page.waitForFunction(
                "key => window.structurizr && structurizr.diagram" +
                    " && structurizr.diagram.getCurrentView()" +
                    " && structurizr.diagram.getCurrentView().key === key" +
                    " && document.querySelectorAll('#diagram .joint-cell').length > 0",
                viewKey
            );

            @SuppressWarnings("unchecked")
            List<Map<String, Object>> bindings =
                (List<Map<String, Object>>) page.evaluate(CAPTURE);
            String svg = (String) page.evaluate(
                "() => structurizr.diagram.exportCurrentDiagramToSVG({" +
                    "metadata: false, crop: false, dimensions: true" +
                    "}).markup"
            );
            Files.writeString(
                bindingsPath,
                new GsonBuilder().serializeNulls().setPrettyPrinting().create().toJson(bindings)
            );
            Files.writeString(svgPath, svg);
            browser.close();
        }
    }
}
