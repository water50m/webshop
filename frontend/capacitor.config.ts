import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.sstore.app',
  appName: 'SStore',
  webDir: 'out',
  android: {
    // Production must use HTTPS.  This flag only permits LAN HTTP while
    // developing against the FastAPI server on the current private network.
    allowMixedContent: false,
  },
  plugins: {
    SocialLogin: {
      providers: {
        facebook: true,
        google: false,
        apple: false,
        twitter: false,
      },
    },
  },
};

export default config;
