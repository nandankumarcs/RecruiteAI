import React, { useState, useRef, useEffect } from "react";
import { Upload, X, FileText, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface ResumeUploaderProps {
  jobId: string;
  onUploadSuccess: () => void;
}

export function ResumeUploader({ jobId, onUploadSuccess }: ResumeUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Simulated progress during parsing
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isUploading && uploadProgress < 90) {
      interval = setInterval(() => {
        setUploadProgress((prev) => {
          const increment = Math.random() * 15;
          return Math.min(prev + increment, 90);
        });
      }, 600);
    }
    return () => clearInterval(interval);
  }, [isUploading, uploadProgress]);

  const addFiles = (newFiles: File[]) => {
    const validFiles = newFiles.filter(
      (file) => file.type === "application/pdf" || file.name.endsWith(".docx")
    );

    if (validFiles.length < newFiles.length) {
      toast.error("Only PDF and DOCX files are allowed");
    }

    setFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      const uniqueNewFiles = validFiles.filter((f) => !existingNames.has(f.name));
      
      if (uniqueNewFiles.length < validFiles.length) {
        toast.info("Duplicate files were skipped");
      }
      
      return [...prev, ...uniqueNewFiles];
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      addFiles(Array.from(e.target.files));
    }
    // Clear input so same file can be selected again if removed
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const uploadResumes = async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    setUploadProgress(10);
    
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      await api.post(`/jobs/${jobId}/resumes`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      setUploadProgress(100);
      setTimeout(() => {
        setFiles([]);
        onUploadSuccess();
        toast.success(`${files.length} resume(s) uploaded and parsed successfully!`);
        setIsUploading(false);
        setUploadProgress(0);
      }, 500);
    } catch (error) {
      console.error("Upload failed", error);
      toast.error("Upload failed. Please check your connection and try again.");
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-all duration-300",
          isDragging 
            ? "border-primary bg-primary/5 scale-[1.01] shadow-inner" 
            : "border-border/60 bg-card/40 hover:border-primary/40 hover:bg-card/60",
          isUploading && "opacity-50 cursor-not-allowed pointer-events-none"
        )}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          multiple
          accept=".pdf,.docx"
          className="hidden"
        />
        <div className="flex flex-col items-center gap-4">
          <div className="p-5 bg-primary/10 rounded-lg text-primary shadow-sm">
            <Upload className="h-10 w-10" />
          </div>
          <div>
            <p className="text-xl font-bold tracking-tight">Drop resumes here</p>
            <p className="text-sm text-muted-foreground font-medium mt-1">PDF or DOCX (max 10MB each)</p>
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className={cn(
          "space-y-4 p-5 rounded-lg border border-border/50 transition-all duration-300",
          isUploading ? "glass border-primary/30" : "bg-card/40"
        )}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold">{files.length} file(s) selected</h4>
              {isUploading && (
                <span className="text-[10px] bg-primary/20 text-primary px-2 py-0.5 rounded-full font-bold animate-pulse uppercase tracking-tighter">
                  Parsing...
                </span>
              )}
            </div>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => setFiles([])} 
              disabled={isUploading}
              className="h-8 text-muted-foreground hover:text-destructive"
            >
              Clear all
            </Button>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
            {files.map((file, i) => (
              <div key={file.name + i} className="flex items-center justify-between p-3 bg-background/50 rounded-lg border border-border/40 group hover:border-primary/30 transition-all">
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="p-2 bg-muted/50 rounded-lg group-hover:bg-primary/10 transition-colors">
                    <FileText className="h-4 w-4 text-muted-foreground group-hover:text-primary" />
                  </div>
                  <div className="flex flex-col overflow-hidden">
                    <span className="text-sm font-semibold truncate leading-none mb-1">{file.name}</span>
                    <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </span>
                  </div>
                </div>
                {!isUploading ? (
                  <button 
                    onClick={(e) => { e.stopPropagation(); removeFile(i); }} 
                    className="p-1.5 rounded-lg hover:bg-destructive/10 hover:text-destructive transition-all"
                  >
                    <X className="h-4 w-4" />
                  </button>
                ) : (
                  uploadProgress === 100 && <CheckCircle2 className="h-4 w-4 text-green-500 animate-in zoom-in" />
                )}
              </div>
            ))}
          </div>

          <div className="space-y-3">
            {isUploading && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest text-primary">
                  <span>Progress</span>
                  <span>{Math.round(uploadProgress)}%</span>
                </div>
                <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary transition-all duration-500 ease-out shadow-[0_0_8px_rgba(var(--primary),0.5)]"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}

            <Button 
              className="w-full h-12 text-base font-bold shadow-md shadow-primary/10 hover:shadow-primary/20 transition-all active:scale-[0.98]" 
              onClick={uploadResumes}
              disabled={isUploading}
            >
              {isUploading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  {uploadProgress < 40 ? "Uploading..." : "Parsing Contents..."}
                </>
              ) : (
                `Process ${files.length} Candidate(s)`
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
