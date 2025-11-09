using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using DeepBridgeWindowsApp.DICOM;

namespace DeepBridgeWindowsApp.Dicom
{
    public class DicomDisplayManager
    {
        public string DirectoryPath => reader.DirectoryPath;
        private readonly DicomReader reader;
        public DicomMetadata[] slices;
        public DicomMetadata globalView { get; private set; }
        private int currentSliceIndex;
        public int windowWidth { get; private set; }
        public int windowCenter { get; private set; }

        public DicomDisplayManager(DicomReader reader)
        {
            this.reader = reader;
            globalView = reader.GlobalView;
            slices = reader.Slices ?? Array.Empty<DicomMetadata>();
            currentSliceIndex = 0;
            windowWidth = slices.Length > 0 ? slices[0].WindowWidth : 0;
            windowCenter = slices.Length > 0 ? slices[0].WindowCenter : 0;
        }

        public DicomMetadata GetSlice(int sliceIndex)
        {
            return slices[sliceIndex];
        }

        public Bitmap GetCurrentSliceImage(int windowWidth = -1, int windowCenter = -1)
        {
            return DicomImageProcessor.ConvertToBitmap(slices[currentSliceIndex], windowWidth, windowCenter);
        }

        public Bitmap GetGlobalViewImage()
        {
            return DicomImageProcessor.ConvertToBitmap(globalView);
        }

        public void SetSliceIndex(int index)
        {
            if (index >= 0 && index < slices.Length)
            {
                currentSliceIndex = index;
            }
        }

        public int GetCurrentSliceIndex() => currentSliceIndex;
        public int GetTotalSlices() => slices.Length;
    }
}
