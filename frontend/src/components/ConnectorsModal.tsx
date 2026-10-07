import { useDialog } from "@/lib/utils"
import { Connectors } from "@/components/Connectors"

type Props = {
  open: boolean
  onClose: () => void
  brain?: string
}

export function ConnectorsModal({ open, onClose, brain }: Props) {
  const sheetRef = useDialog<HTMLDivElement>(open, onClose)

  if (!open) return null

  return (
    <div
      className="km-scrim"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="km-sheet max-w-[840px] w-full max-h-[88vh] overflow-y-auto p-0 rounded-2xl relative"
        ref={sheetRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Connectors"
      >
        <button
          type="button"
          className="km-x absolute top-5 right-5 z-20 text-lg hover:bg-wash p-1.5 rounded-lg transition-colors"
          onClick={onClose}
          aria-label="Close connectors"
        >
          ✕
        </button>
        <div className="pt-2">
          <Connectors brain={brain} onClose={onClose} />
        </div>
      </div>
    </div>
  )
}
