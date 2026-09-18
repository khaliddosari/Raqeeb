// The dispatch conversation held here in the browser, instead of over the phone.
//
// The visitor plays the authority: Raqeeb speaks the same Arabic briefing it reads down a phone
// line, hears their reply through the microphone, and records their decision with the same tool.
// Audio goes straight from this page to OpenAI over WebRTC; Raqeeb's server only mints the
// short-lived client secret and takes back the result.
//
// The API key never reaches this file. The secret it uses is minted per incident, carries that
// incident's instructions, expires by itself, and is refused a second time by the backend.

const CALLS_URL = "https://api.openai.com/v1/realtime/calls"
const TOOL_NAME = "record_dispatch_confirmation"

// Returned to the model when it records a decision before anyone on the line has said a word,
// which it does: seen on a live call, it recorded a confirmation while the other side was still
// silent. Mirrors _NO_DECISION_HEARD in agent/voice/sip_authority_call.py, which holds the phone
// path to the same rule.
const NO_DECISION_HEARD =
  "لم يُسجَّل شيء: لم يتكلّم أحد من الجهة بعد، فلا يوجد قرار. " +
  "تأكّد أن من على الخط شخص من الجهة، وأكمل البلاغ، ولا تستدعِ الأداة إلا بعد أن تسمع قرارهم."

export type CallLine = { id: string; role: "assistant" | "authority"; text: string; final: boolean }

export type CallDecision = { confirmed: boolean; statement: string }

export type BrowserCallHandlers = {
  /** a line as it is being spoken; the same id arrives again as it grows */
  onLine: (line: CallLine) => void
  /** the authority's decision, the moment the model records it */
  onDecision: (decision: CallDecision) => void
  /** the conversation is over, for any reason */
  onEnd: (reason: "ended" | "timeout" | "error") => void
}

export type BrowserCall = {
  /** hang up; safe to call twice */
  stop: () => void
}

export class MicrophoneDenied extends Error {}

type Line = { role: "assistant" | "authority"; text: string; final: boolean }

/** Opens the microphone and connects it to the incident's conversation. */
export async function startBrowserCall(
  clientSecret: string,
  maxSeconds: number,
  handlers: BrowserCallHandlers,
): Promise<BrowserCall> {
  let microphone: MediaStream
  try {
    microphone = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (error) {
    throw new MicrophoneDenied(String(error))
  }

  const connection = new RTCPeerConnection()
  const speaker = document.createElement("audio")
  speaker.autoplay = true
  const lines = new Map<string, Line>()
  let stopped = false
  let timer = 0

  const publish = (id: string, role: "assistant" | "authority", update: (line: Line) => void) => {
    const line = lines.get(id) ?? { role, text: "", final: false }
    update(line)
    lines.set(id, line)
    handlers.onLine({ id, ...line })
  }

  const stop = (reason: "ended" | "timeout" | "error" = "ended") => {
    if (stopped) return
    stopped = true
    window.clearTimeout(timer)
    for (const line of lines.values()) line.final = true
    microphone.getTracks().forEach((track) => track.stop())
    try {
      connection.close()
    } catch {
      // already closed
    }
    speaker.srcObject = null
    handlers.onEnd(reason)
  }

  connection.ontrack = (event) => {
    speaker.srcObject = event.streams[0]
  }
  connection.addTrack(microphone.getAudioTracks()[0], microphone)
  // the other party hanging up, or the network dropping, ends the conversation here too
  connection.onconnectionstatechange = () => {
    if (["failed", "closed", "disconnected"].includes(connection.connectionState)) stop("ended")
  }

  const channel = connection.createDataChannel("oai-events")
  const answerTool = (callId: string, output: Record<string, unknown>) => {
    channel.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: { type: "function_call_output", call_id: callId, output: JSON.stringify(output) },
      }),
    )
    channel.send(JSON.stringify({ type: "response.create" }))
  }
  channel.addEventListener("message", (event) => {
    let message: Record<string, any>
    try {
      message = JSON.parse(event.data)
    } catch {
      return
    }
    if (import.meta.env.DEV) console.debug("realtime", message.type)
    switch (message.type) {
      // the authority's turn, claimed when it is committed so it keeps its place in the
      // conversation even though its transcription arrives later
      case "input_audio_buffer.committed":
        publish(message.item_id, "authority", () => {})
        break
      case "conversation.item.input_audio_transcription.delta":
        publish(message.item_id, "authority", (line) => (line.text += message.delta ?? ""))
        break
      case "conversation.item.input_audio_transcription.completed":
        publish(message.item_id, "authority", (line) => {
          if (message.transcript) line.text = message.transcript
          line.final = true
        })
        break
      case "response.output_audio_transcript.delta":
        publish(message.item_id, "assistant", (line) => (line.text += message.delta ?? ""))
        break
      case "response.output_audio_transcript.done":
        publish(message.item_id, "assistant", (line) => {
          if (message.transcript) line.text = message.transcript
          line.final = true
        })
        break
      case "response.function_call_arguments.done": {
        if (message.name !== TOOL_NAME) break
        if (![...lines.values()].some((line) => line.role === "authority")) {
          // a decision nobody has spoken is not one: refuse it and let the call carry on
          answerTool(message.call_id, { recorded: false, reason: NO_DECISION_HEARD })
          break
        }
        let args: { confirmed?: boolean; statement?: string } = {}
        try {
          args = JSON.parse(message.arguments || "{}")
        } catch {
          // a decision we cannot read is no decision
        }
        handlers.onDecision({ confirmed: Boolean(args.confirmed), statement: String(args.statement ?? "") })
        // let the call close politely, exactly as the phone path does, rather than cutting the
        // line the instant a decision lands
        answerTool(message.call_id, { acknowledged: true })
        break
      }
      case "error":
        console.error("realtime error", message.error)
        break
    }
  })
  // an outbound call: Raqeeb speaks first rather than waiting for a greeting that never comes
  channel.addEventListener("open", () => channel.send(JSON.stringify({ type: "response.create" })))

  try {
    const offer = await connection.createOffer()
    await connection.setLocalDescription(offer)
    const answer = await fetch(CALLS_URL, {
      method: "POST",
      body: offer.sdp,
      headers: { Authorization: `Bearer ${clientSecret}`, "Content-Type": "application/sdp" },
    })
    if (!answer.ok) throw new Error(`realtime call refused: ${answer.status}`)
    await connection.setRemoteDescription({ type: "answer", sdp: await answer.text() })
  } catch (error) {
    stop("error")
    throw error
  }

  // a ceiling on one conversation, so an abandoned tab cannot hold a session open
  timer = window.setTimeout(() => stop("timeout"), maxSeconds * 1000)
  return { stop: () => stop("ended") }
}
