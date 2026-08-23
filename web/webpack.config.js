const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');

module.exports = (env, argv) => {
  const isDev = argv.mode !== 'production';

  return {
    mode: isDev ? 'development' : 'production',
    entry: './src/index.tsx',
    output: {
      path: path.resolve(__dirname, 'dist'),
      filename: 'bundle.[contenthash:8].js',
      chunkFilename: '[name].[contenthash:8].js',
      publicPath: 'auto',
      clean: true,
    },
    devtool: isDev ? 'eval-source-map' : false,
    optimization: {
      splitChunks: {
        chunks: 'all',
      },
    },
    module: {
      rules: [
        {
          test: /\.mjs$/,
          include: /node_modules/,
          type: 'javascript/auto',
          resolve: { fullySpecified: false },
        },
        {
          test: /\.(ts|tsx|js|jsx)$/,
          exclude: /node_modules/,
          use: {
            loader: 'babel-loader',
            options: {
              presets: [
                ['@babel/preset-react', { runtime: 'automatic', development: isDev }],
                '@babel/preset-env',
                '@babel/preset-typescript',
              ],
            },
          },
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader', 'postcss-loader'],
        },
        {
          test: /\.(png|jpe?g|gif|webp|ico|svg)$/i,
          type: 'asset',
          parser: { dataUrlCondition: { maxSize: 8 * 1024 } },
        },
        {
          test: /\.(woff2?|eot|ttf|otf)$/i,
          type: 'asset/resource',
        },
        {
          exclude: /\.(js|jsx|ts|tsx|mjs|css|json|html)$/i,
          type: 'asset/resource',
        },
      ],
    },
    resolve: {
      extensions: ['.mjs', '.ts', '.tsx', '.js', '.jsx'],
      alias: {
        '@': path.resolve(__dirname, 'src'),
        '@domain': path.resolve(__dirname, 'src/domain'),
        '@features': path.resolve(__dirname, 'src/features'),
        '@components': path.resolve(__dirname, 'src/components'),
        '@design-system': path.resolve(__dirname, 'src/design-system'),
      },
    },
    devServer: {
      port: 3290,
      allowedHosts: 'all',
      historyApiFallback: true,
      proxy: [
        {
          context: ['/api', '/ping'],
          target: 'http://localhost:8772',
          changeOrigin: true,
        },
      ],
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: './index.html',
        inject: 'body',
      }),
      new CopyWebpackPlugin({
        patterns: [
          { from: 'public/assets', to: 'assets' },
          { from: 'public/favicon.ico', to: 'favicon.ico' },
          { from: 'public/desktop-icon.ico', to: 'desktop-icon.ico' },
        ],
      }),
    ],
  };
};
