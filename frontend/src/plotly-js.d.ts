/** plotly.js ships no bundled types; only the surface used by figureExport
 *  (newPlot / toImage / purge on a detached graph div) is declared here. */
declare module "plotly.js/dist/plotly.min.js" {
  export interface PlotlyStatic {
    newPlot(
      el: HTMLElement,
      data: unknown[],
      layout: unknown,
      config?: unknown,
    ): Promise<unknown>;
    toImage(
      el: HTMLElement,
      opts: { format?: string; width?: number; height?: number; scale?: number },
    ): Promise<string>;
    purge(el: HTMLElement): void;
  }
  const Plotly: PlotlyStatic;
  export default Plotly;
}
