import { createBrowserRouter } from "react-router-dom";
import { App } from "./App";

const raw = import.meta.env.BASE_URL;
const basename = raw === "/" ? "/" : raw.endsWith("/") ? raw.slice(0, -1) : raw;

export const router = createBrowserRouter([{ path: "/", element: <App /> }], { basename });
