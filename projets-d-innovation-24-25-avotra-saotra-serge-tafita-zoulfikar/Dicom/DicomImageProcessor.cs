using System;
using System.Collections.Generic;
using System.Drawing.Imaging;
using System.Drawing;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

namespace DeepBridgeWindowsApp.Dicom
{
    public class DicomImageProcessor
    {
        public static Bitmap ConvertToBitmap(DicomMetadata metadata, int windowWidth = -1, int windowCenter = -1)
        {
            if (windowWidth == -1)
            {
                windowWidth = metadata.WindowWidth;
            }
            if (windowCenter == -1)
            {
                windowCenter = metadata.WindowCenter;
            }

            var pixelDataArray = metadata.PixelData.ToArray();
            var outputData = new byte[metadata.Rows * metadata.Columns * 4];
            var mask = (ushort)(ushort.MaxValue >> (metadata.BitsAllocated - metadata.BitsStored));
            var maxValue = Math.Pow(2, metadata.BitsStored);
            var windowHalf = ((windowWidth - 1) / 2.0) - 0.5;

            int outputIndex = 0;
            for (int i = 0; i < pixelDataArray.Length; i += 2)
            {
                ushort pixelValue = (ushort)((pixelDataArray[i]) | (pixelDataArray[i + 1] << 8));
                double hounsfield = pixelValue & mask;

                if (metadata.PixelRepresentation == 1 && hounsfield > (maxValue / 2))
                {
                    hounsfield = hounsfield - maxValue;
                }

                hounsfield = metadata.RescaleSlope * hounsfield + metadata.RescaleIntercept;

                byte intensity;
                if (hounsfield <= windowCenter - windowHalf)
                    intensity = 0;
                else if (hounsfield >= windowCenter + windowHalf)
                    intensity = 255;
                else
                    intensity = (byte)(((hounsfield - (windowCenter - 0.5)) / (windowWidth - 1) + 0.5) * 255);

                outputData[outputIndex++] = intensity;
                outputData[outputIndex++] = intensity;
                outputData[outputIndex++] = intensity;
                outputData[outputIndex++] = 255;
            }

            var bitmap = new Bitmap(metadata.Columns, metadata.Rows, PixelFormat.Format32bppArgb);
            var bitmapData = bitmap.LockBits(
                new Rectangle(0, 0, metadata.Columns, metadata.Rows),
                ImageLockMode.WriteOnly,
                PixelFormat.Format32bppArgb);

            Marshal.Copy(outputData, 0, bitmapData.Scan0, outputData.Length);
            bitmap.UnlockBits(bitmapData);

            return bitmap;
        }
    }
}
