import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Loader2 } from "lucide-react";

interface DeleteConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  isLoading?: boolean;
}

export function DeleteConfirmDialog({ 
  isOpen, 
  onClose, 
  onConfirm, 
  title, 
  description,
  isLoading = false 
}: DeleteConfirmDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md p-0 overflow-hidden bg-background/95 backdrop-blur-2xl border-border/40 shadow-2xl animate-in fade-in zoom-in-95 duration-200 rounded-lg">
        <div className="p-8 space-y-6">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="p-4 bg-destructive/10 rounded-lg text-destructive shadow-inner animate-bounce-subtle">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <div className="space-y-2">
              <DialogTitle className="text-2xl font-black tracking-tight font-display">
                {title}
              </DialogTitle>
              <DialogDescription className="text-sm font-medium leading-relaxed text-muted-foreground px-4">
                {description}
              </DialogDescription>
            </div>
          </div>

          <div className="flex flex-col gap-3 pt-2">
            <Button 
              variant="destructive" 
              size="lg"
              onClick={onConfirm} 
              disabled={isLoading}
              className="w-full h-14 rounded-lg font-black tracking-tight shadow-md shadow-destructive/20 hover:scale-[1.02] active:scale-95 transition-all"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  PROCESSING...
                </>
              ) : (
                "CONFIRM DELETION"
              )}
            </Button>
            <Button 
              variant="ghost" 
              size="lg"
              onClick={onClose} 
              disabled={isLoading}
              className="w-full h-12 rounded-lg font-bold text-muted-foreground hover:bg-muted/50"
            >
              Cancel
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
