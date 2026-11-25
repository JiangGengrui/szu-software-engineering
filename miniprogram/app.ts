import { auth } from './core/auth';
App({ onLaunch() { void auth.confirm().catch(() => undefined); } });
