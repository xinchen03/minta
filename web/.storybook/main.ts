import type { StorybookConfig } from "@storybook/react-webpack5";
import path from "path";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-essentials", "@storybook/addon-a11y"],
  framework: {
    name: "@storybook/react-webpack5",
    options: {},
  },
  core: {
    builder: "webpack5",
  },
  staticDirs: ["../public"],
  webpackFinal: async (config) => {
    config.module = config.module || { rules: [] };
    config.module.rules = config.module.rules || [];
    // Drop implicit CSS rules so the project's postcss/tailwind chain applies once.
    config.module.rules = config.module.rules.filter(
      (rule) => !(rule && rule.test && rule.test instanceof RegExp && rule.test.test("x.css")),
    );
    config.module.rules.push(
      {
        test: /\.(ts|tsx|js|jsx)$/,
        exclude: /node_modules/,
        use: {
          loader: "babel-loader",
          options: {
            presets: [
              ["@babel/preset-react", { runtime: "automatic" }],
              "@babel/preset-env",
              "@babel/preset-typescript",
            ],
          },
        },
      },
      {
        test: /\.css$/,
        use: [
          require.resolve("style-loader"),
          require.resolve("css-loader"),
          require.resolve("postcss-loader"),
        ],
      },
    );
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias as Record<string, string>),
      "@": path.resolve(__dirname, "../src"),
      "@design-system": path.resolve(__dirname, "../src/design-system"),
    };
    return config;
  },
};

export default config;
