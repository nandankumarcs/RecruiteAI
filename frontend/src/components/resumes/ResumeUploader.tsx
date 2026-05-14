import React, { useState, useRef, useEffect } from "react";
import { Upload, X, FileText, Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useResumeProgressStream } from "@/hooks/useResumeProgressStream";

interface ResumeUploaderProps {
  jobId: string;
  onUploadSuccess: () => void;
}

export function ResumeUploader({ jobId, onUploadSuccess }: ResumeUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Use SSE streaming hook for real-time progress
  const { resumes: progressResumes, isConnected, isComplete, error: streamError } = 
    useResumeProgressStream(jobId, sessionId);

  // Handle completion
  useEffect(() => {
    if (isComplete && progressResumes.length > 0) {
      const successCount = progressResumes.filter(r => r.status === 'completed').length;
      const errorCount = progressResumes.filter(r => r.status === 'error').length;
      
      setTimeout(() => {
        setFiles([]);
        setSessionId(null);
        setIsUploading(false);
        onUploadSuccess();
        
        if (errorCount === 0) {
          toast.success(`${successCount} resume(s) processed successfully!`);
        } else {
          toast.warning(`${successCount} succeeded, ${errorCount} failed`);
        }
      }, 1000);
    }
  }, [isComplete, progressResumes, onUploadSuccess]);

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
    
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("files", file);
    });

    try {
      // Upload files and receive session_id
      const response = await api.post(`/jobs/${jobId}/resumes`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      
      // Set session_id to start SSE streaming
      setSessionId(response.data.session_id);
    } catch (error) {
      console.error("Upload failed", error);
      toast.error("Upload failed. Please check your connection and try again.");
      setIsUploading(false);
      setSessionId(null);
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
              {isUploading && !isComplete && (
                <span className="text-[10px] bg-primary/20 text-primary px-2 py-0.5 rounded-full font-bold animate-pulse uppercase tracking-tighter">
                  Processing...
                </span>
              )}
              {isComplete && (
                <span className="text-[10px] bg-green-500/20 text-green-600 px-2 py-0.5 rounded-full font-bold uppercase tracking-tighter">
                  Complete
                </span>
              )}
            </div>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={() => {
                setFiles([]);
                setSessionId(null);
                setIsUploading(false);
              }} 
              disabled={isUploading && !isComplete}
              className="h-8 text-muted-foreground hover:text-destructive"
            >
              Clear all
            </Button>
          </div>

          {/* Connection status */}
          {isUploading && streamError && (
            <div className="flex items-center gap-2 p-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-yellow-600 text-xs">
              <Clock className="h-3 w-3" />
              <span>{streamError}</span>
            </div>
          )}

          <div className="space-y-2 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
            {/* Show real-time progress if streaming is active */}
            {isUploading && progressResumes.length > 0 ? (
              progressResumes.map((resume, i) => (
                <div 
                  key={i} 
                  className={cn(
                    "flex items-center justify-between p-3 rounded-lg border transition-all",
                    resume.status === 'completed' && "bg-green-500/5 border-green-500/20",
                    resume.status === 'error' && "bg-red-500/5 border-red-500/20",
                    !['completed', 'error'].includes(resume.status) && "bg-background/50 border-border/40"
                  )}
                >
                  <div className="flex items-center gap-3 overflow-hidden flex-1">
                    <div className={cn(
                      "p-2 rounded-lg transition-colors",
                      resume.status === 'completed' && "bg-green-500/10",
                      resume.status === 'error' && "bg-red-500/10",
                      !['completed', 'error'].includes(resume.status) && "bg-muted/50"
                    )}>
                      {resume.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-green-600" />}
                      {resume.status === 'error' && <XCircle className="h-4 w-4 text-red-600" />}
                      {!['completed', 'error'].includes(resume.status) && <FileText className="h-4 w-4 text-muted-foreground" />}
                    </div>
                    <div className="flex flex-col overflow-hidden flex-1">
                      <span className="text-sm font-semibold truncate leading-none mb-1">
                        {resume.filename}
                      </span>
                      <div className="text-[10px] text-muted-foreground font-medium">
                        {resume.status === 'completed' && resume.candidateName && (
                          <span className="text-green-600 font-bold">
                            ✓ {resume.candidateName}
                            {resume.matchingScore !== undefined && ` (${Math.round(resume.matchingScore)}% match)`}
                          </span>
                        )}
                        {resume.status === 'error' && (
                          <span className="text-red-600 font-bold">
                            ✗ {resume.errorMessage || 'Processing failed'}
                          </span>
                        )}
                        {resume.status === 'pending' && (
                          <span className="text-muted-foreground uppercase tracking-wider">Pending...</span>
                        )}
                        {resume.status === 'starting' && (
                          <span className="text-primary uppercase tracking-wider">Starting...</span>
                        )}
                        {resume.status === 'uploading' && (
                          <span className="text-primary uppercase tracking-wider">Uploading...</span>
                        )}
                        {resume.status === 'parsing' && (
                          <span className="text-primary uppercase tracking-wider">Parsing...</span>
                        )}
                        {resume.status === 'evaluating' && (
                          <span className="text-primary uppercase tracking-wider">Evaluating...</span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="ml-2">
                    {resume.status === 'completed' && (
                      <CheckCircle2 className="h-5 w-5 text-green-500 animate-in zoom-in" />
                    )}
                    {resume.status === 'error' && (
                      <XCircle className="h-5 w-5 text-red-500 animate-in zoom-in" />
                    )}
                    {!['completed', 'error', 'pending'].includes(resume.status) && (
                      <Loader2 className="h-5 w-5 text-primary animate-spin" />
                    )}
                  </div>
                </div>
              ))
            ) : (
              // Show file list before upload starts
              files.map((file, i) => (
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
                  {!isUploading && (
                    <button 
                      onClick={(e) => { e.stopPropagation(); removeFile(i); }} 
                      className="p-1.5 rounded-lg hover:bg-destructive/10 hover:text-destructive transition-all"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>

          <div className="space-y-3">
            {/* Show completion summary */}
            {isComplete && progressResumes.length > 0 && (
              <div className="p-3 bg-muted/30 rounded-lg border border-border/40">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-muted-foreground">Summary:</span>
                  <div className="flex gap-4">
                    <span className="text-green-600 font-bold">
                      {progressResumes.filter(r => r.status === 'completed').length} succeeded
                    </span>
                    {progressResumes.filter(r => r.status === 'error').length > 0 && (
                      <span className="text-red-600 font-bold">
                        {progressResumes.filter(r => r.status === 'error').length} failed
                      </span>
                    )}
                  </div>
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
                  Processing {progressResumes.filter(r => r.status === 'completed' || r.status === 'error').length} / {files.length}
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
