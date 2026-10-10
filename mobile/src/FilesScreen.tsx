import { Ionicons } from '@expo/vector-icons';
import { File, Directory, Paths } from 'expo-file-system';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View, ActivityIndicator } from 'react-native';
import type { ClicxMessage } from './protocol';
import { GlassCard, ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  sendString: (data: string) => void;
  sendBinary: (data: ArrayBuffer | Uint8Array) => void;
  onBinary: (cb: (data: ArrayBuffer) => void) => () => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  onBack: () => void;
};

type PcFile = { name: string; size: number };

const CHUNK = 64 * 1024;
const PHONE_DIR = 'ClicX recibidos';

/**
 * Derive a clean, host-safe basename for an upload.
 *
 * `file.name` may be missing on the installed bundle, and `Paths.basename`
 * on an Android content URI includes the storage-claim prefix (e.g.
 * "primary:prueba.txt" for /sdcard/prueba.txt) which the host rejects as
 * "bad name" (':' is not allowed in a file name). We strip the volume prefix
 * and any remaining illegal characters so the host always receives a valid,
 * single-segment basename. Host-side security validation is NOT relaxed.
 */
function pickedFileName(file: { uri: string }): string {
  let base = '';
  try {
    base = Paths.basename(file.uri).trim();
  } catch {
    base = '';
  }
  // Android exposes the name as "<volume>:<name>". Keep only the name part.
  const lastColon = base.lastIndexOf(':');
  let clean = lastColon >= 0 ? base.slice(lastColon + 1) : base;
  clean = clean.replace(/[:\\]/g, '_').replace(/\x00/g, '').replace(/^[. ]+/, '');
  if (!clean) clean = `archivo${Date.now()}`;
  return clean;
}


/** Centro de control → Archivos. Enviar archivos a la PC y recibir desde la PC. */
export function FilesScreen({ send, sendBinary, onBinary, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [pcFiles, setPcFiles] = useState<PcFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [dlActive, setDlActive] = useState(false);
  const dlHandleRef = useRef<ReturnType<File['open']> | null>(null);
  const dlMetaRef = useRef<{ id: string; name: string; size: number } | null>(null);
  const dlPendingRef = useRef<{ size: number } | null>(null);
  const dlWrittenRef = useRef(0);

  const flash = (msg: string) => {
    setStatus(msg);
    setTimeout(() => setStatus(''), 2500);
  };

  // Replies: list + file control messages.
  useEffect(() => {
    return onReply((data) => {
      if (data?.t !== 'file') return;
      const action = data.action;
      if (action === 'list' && Array.isArray(data.files)) {
        setPcFiles(data.files as PcFile[]);
      } else if (action === 'meta_ack') {
        // upload staged → proceed is driven by the upload loop.
      } else if (action === 'chunk_ack') {
        // upload chunk accepted → loop resumes.
        if (typeof data.id === 'string') resumeUpload(data.id);
      } else if (action === 'done_ack') {
        setBusy(false);
        setDlActive(false);
        flash('Archivo recibido/guardado en la PC');
      } else if (action === 'done' && data.ok) {
        // download finished: close and finalize phone file
        finishDownload().catch(() => {});
      } else if (action === 'meta' && data.ok) {
        // download metadata announced (id, name, size)
        setBusy(true);
        setDlActive(true);
        dlMetaRef.current = { id: String(data.id), name: String(data.name), size: Number(data.size) };
        dlWrittenRef.current = 0;
        openDownloadHandle(String(data.name))
          .then(() => {
            // ask for the first chunk
            const id = dlMetaRef.current!.id;
            send(pullMsg(id, Math.min(CHUNK, dlMetaRef.current!.size)));
          })
          .catch((e) => {
            setBusy(false);
            setDlActive(false);
            flash(`No se pudo guardar: ${e instanceof Error ? e.message : 'error'}`);
          });
      } else if (action === 'chunk' && data.ok) {
        // host will send the binary right after → note expected offset/size
        dlPendingRef.current = { size: Number(data.size) };
      } else if (data.ok === false) {
        setBusy(false);
        setDlActive(false);
        closeDownloadHandle().catch(() => {});
        flash(String(data.error ?? 'Error') + (data.id ? ` (${data.id})` : ''));
      }
    });
  }, [onReply, send]);

  // Binary frames = download chunks.
  useEffect(() => {
    return onBinary((buf) => {
      const pending = dlPendingRef.current;
      if (!pending) return;
      dlPendingRef.current = null;
      const bytes = new Uint8Array(buf);
      const h = dlHandleRef.current;
      if (!h) return;
      try {
        h.writeBytes(bytes);
      } catch {
        return;
      }
      dlWrittenRef.current += bytes.length;
      const meta = dlMetaRef.current;
      if (meta && dlHandleRef.current) {
        // Always request another pull; the host clamps to what remains and
        // replies `done` once the source is exhausted (finalizes the file).
        send(pullMsg(meta.id, CHUNK));
      }
    });
  }, [onBinary, send]);

  const pullMsg = useCallback(
    (id: string, size: number): ClicxMessage => ({ t: 'file', action: 'pull', id, size }),
    [],
  );

  const listPc = useCallback(() => {
    send({ t: 'file', action: 'list', folder: 'from_pc' });
  }, [send]);

  useEffect(() => {
    listPc();
  }, [listPc]);

  useEffect(() => {
    return () => {
      closeDownloadHandle().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const uploadOne = useCallback(
    async (file: File, id: string, bytes: Uint8Array) => {
      const name = pickedFileName(file);
      const size = bytes.byteLength;
      // stream the in-memory bytes in chunks (enqueueUpload sends the meta)
      enqueueUpload({ id, name, size, data: bytes });
    },
    [send],
  );

  // ---- upload: chunked streaming of a picked file's bytes, driven by chunk_ack ----
  // The Android picker returns a `content://` URI. The low-level handle API
  // (`File.open()`/`readBytes`) rejects content URIs, so we read the selected
  // file once via `File.bytes()` (which resolves content URIs through the
  // content resolver) and then stream those bytes in binary chunks over the
  // wire. The control protocol stays JSON meta/chunk/done + raw binary chunks.
  const uploadQueueRef = useRef<{ id: string; name: string; size: number; data: Uint8Array } | null>(null);
  const uploadPosRef = useRef(0);

  const enqueueUpload = (job: { id: string; name: string; size: number; data: Uint8Array }) => {
    uploadQueueRef.current = job;
    uploadPosRef.current = 0;
    setBusy(true);
    send({ t: 'file', action: 'meta', id: job.id, name: job.name, size: job.size });
    // send first chunk right away; subsequent driven by chunk_ack
    nextUploadChunk();
  };

  const nextUploadChunk = () => {
    const job = uploadQueueRef.current;
    if (!job) return;
    const remaining = job.size - uploadPosRef.current;
    if (remaining <= 0) {
      send({ t: 'file', action: 'done', id: job.id });
      uploadQueueRef.current = null;
      return;
    }
    const take = Math.min(CHUNK, remaining);
    const offset = uploadPosRef.current;
    const bytes = job.data.subarray(offset, offset + take);
    uploadPosRef.current += bytes.length;
    send({ t: 'file', action: 'chunk', id: job.id, offset, size: bytes.length });
    if (bytes.length > 0) sendBinary(bytes);
    if (bytes.length < take) {
      // short read → end
      send({ t: 'file', action: 'done', id: job.id });
      uploadQueueRef.current = null;
    }
  };

  const resumeUpload = (id: string) => {
    if (uploadQueueRef.current?.id === id) nextUploadChunk();
  };

  const pickAndUpload = async () => {
    if (busy || dlActive) {
      flash('Esperá a que termine la operación actual');
      return;
    }
    try {
      const res = await File.pickFileAsync();
      const files = Array.isArray(res) ? res : res ? [res] : [];
      if (files.length === 0) return;
      for (let i = 0; i < files.length; i++) {
        const file = files[i] as unknown as File;
        // Read via File.bytes(): SAF-safe for content:// URIs (no base64).
        const bytes = await file.bytes();
        await uploadOne(file, `u${Date.now()}-${i}`, bytes);
        await new Promise((r) => setTimeout(r, 300));
        while (uploadQueueRef.current) await new Promise((r) => setTimeout(r, 200));
      }
    } catch (e) {
      flash(`No se pudo abrir: ${e instanceof Error ? e.message : 'error'}`);
    }
  };

  // ---- download helpers ----
  const openDownloadHandle = async (name: string) => {
    const dir = new Directory(Paths.document, PHONE_DIR);
    try {
      dir.create();
    } catch {
      // already exists
    }
    const target = dir.createFile(name, null);
    dlHandleRef.current = target.open();
    return dlHandleRef.current;
  };

  const closeDownloadHandle = async () => {
    const h = dlHandleRef.current;
    dlHandleRef.current = null;
    dlPendingRef.current = null;
    dlMetaRef.current = null;
    if (h) {
      try {
        h.close();
      } catch {
        // ignore
      }
    }
  };

  const finishDownload = async () => {
    const h = dlHandleRef.current;
    dlHandleRef.current = null;
    dlPendingRef.current = null;
    if (h) {
      try {
        h.close();
      } catch {
        // ignore
      }
    }
    setBusy(false);
    setDlActive(false);
    flash('Archivo guardado en el teléfono');
  };

  const downloadOne = (f: PcFile) => {
    if (busy || dlActive) {
      flash('Esperá a que termine la operación actual');
      return;
    }
    setBusy(true);
    send({ t: 'file', action: 'download', id: `d${Date.now()}`, name: f.name });
  };

  return (
    <ScreenChrome title="Archivos" subtitle="Carpetas ClicX: From Phone / From PC" onBack={onBack}>
      <GlassCard>
        <Text style={styles.cardTitle}>Enviar a la PC</Text>
        <Text style={styles.hint}>Se guarda en %LOCALAPPDATA%/ClicX/From Phone</Text>
        <Pressable style={styles.bigBtn} onPress={pickAndUpload} disabled={busy}>
          <Ionicons name="cloud-upload-outline" size={20} color={THEME.label} />
          <Text style={styles.bigBtnLabel}>Elegir archivo y enviar</Text>
        </Pressable>
      </GlassCard>

      <GlassCard>
        <View style={styles.titleRow}>
          <Text style={styles.cardTitle}>Desde la PC</Text>
          <Pressable onPress={listPc} hitSlop={8}>
            <Ionicons name="refresh-outline" size={18} color={THEME.label} />
          </Pressable>
        </View>
        {pcFiles.length === 0 ? (
          <Text style={styles.empty}>Carpeta ClicX/From PC vacía.</Text>
        ) : (
          pcFiles.map((f) => (
            <Pressable key={f.name} style={styles.fileRow} onPress={() => downloadOne(f)}>
              <Ionicons name="document-outline" size={18} color={THEME.label} />
              <View style={styles.fileInfo}>
                <Text style={styles.fileName} numberOfLines={1}>
                  {f.name}
                </Text>
                <Text style={styles.fileMeta}>{formatSize(f.size)}</Text>
              </View>
              <Ionicons name="download-outline" size={18} color={THEME.label} />
            </Pressable>
          ))
        )}
      </GlassCard>

      {busy ? (
        <View style={styles.busyRow}>
          <ActivityIndicator color={THEME.orange} />
          <Text style={styles.busyText}>{dlActive ? 'Recibiendo…' : 'Enviando…'}</Text>
        </View>
      ) : null}
      {status ? <Text style={styles.status}>{status}</Text> : null}
    </ScreenChrome>
  );
}

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    cardTitle: {
      color: THEME.label,
      fontSize: 14,
      fontWeight: '600',
      marginBottom: 6,
    },
    hint: {
      color: THEME.secondary,
      fontSize: 11,
      marginBottom: 12,
    },
    bigBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      backgroundColor: THEME.orangeDeep,
      borderRadius: 12,
      paddingVertical: 14,
    },
    bigBtnLabel: {
      color: THEME.label,
      fontSize: 14,
      fontWeight: '600',
    },
    titleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    empty: {
      color: THEME.tertiary,
      fontSize: 13,
      textAlign: 'center',
      marginTop: 12,
    },
    fileRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      backgroundColor: THEME.canvas,
      borderRadius: 10,
      padding: 12,
      marginBottom: 8,
    },
    fileInfo: {
      flex: 1,
    },
    fileName: {
      color: THEME.label,
      fontSize: 13,
    },
    fileMeta: {
      color: THEME.tertiary,
      fontSize: 11,
      marginTop: 2,
    },
    busyRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      marginTop: 8,
    },
    busyText: {
      color: THEME.secondary,
      fontSize: 13,
    },
    status: {
      color: THEME.orange,
      fontSize: 12,
      textAlign: 'center',
      marginTop: 8,
      fontWeight: '600',
    },
  });
