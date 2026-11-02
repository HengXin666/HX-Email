import { spawnSync } from 'node:child_process'
import { realpathSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export function runGate(args: string[]): never {
  const here = fileURLToPath(new URL('.', import.meta.url))
  const result = spawnSync('uv', ['run', '--with-requirements', here + 'requirements.txt',
    'python', here + 'verify.py', ...args], { stdio: 'inherit' })
  if (result.error) console.error(result.error.message)
  process.exit(result.status ?? 2)
}

// Run the gate when this file is the entry, e.g. node run.ts --staged; importers such as cli/verify-all.ts call runGate themselves
const entry = process.argv[1]
if (entry && realpathSync(entry) === realpathSync(fileURLToPath(import.meta.url))) {
  runGate(process.argv.slice(2))
}
