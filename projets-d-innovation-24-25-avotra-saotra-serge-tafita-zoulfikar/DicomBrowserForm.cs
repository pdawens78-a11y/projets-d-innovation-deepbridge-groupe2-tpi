using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using WinForms = System.Windows.Forms;
using DeepBridgeWindowsApp.Dicom;
using DeepBridgeWindowsApp.DICOM;

namespace DeepBridgeWindowsApp
{
    public partial class DicomBrowserForm : Form
    {
        private string currentDirectory;
        private readonly string defaultDirectory = @"D:\dataset_chu_nice_2020_2021\scan\SF103E8_10.241.3.232_20210118173900817_CT\SF103E8_10.241.3.232_20210118173900817";
        //private readonly string defaultDirectory = @"C:\dataset_chu_nice_2020_2021\scan\SF103E8_10.241.3.232_20210118173228207_CT_SR\SF103E8_10.241.3.232_20210118173228207";
        //private readonly string defaultDirectory = @"C:\dataset_chu_nice_2020_2021\scan\SF103E8_10.241.3.232_20210118174910223_CT\SF103E8_10.241.3.232_20210118174910223";
        private Panel rightPanel;
        private ListView contentListView;
        private Button viewDicomButton;
        private TextBox directoryTextBox;
        private Label infoLabel;
        private TableLayoutPanel mainTableLayout;
        private PictureBox globalViewPictureBox;

        public DicomBrowserForm()
        {
            InitializeComponents();
            currentDirectory = defaultDirectory;
            LoadDirectory(currentDirectory);
        }

        private void InitializeComponents()
        {
            // Form settings
            Text = "DICOM Viewer - Main";
            Size = new System.Drawing.Size(1000, 600);
            MinimumSize = new System.Drawing.Size(800, 400);  // Set minimum size to prevent layout issues

            // Create main table layout
            mainTableLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 2,
                Padding = new Padding(10),
            };

            // Configure row and column styles
            mainTableLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));  // Top controls
            mainTableLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));  // Main content

            // Top panel for directory controls
            var topPanel = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 2,
                RowCount = 1,
                Margin = new Padding(0)
            };
            topPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 85));
            topPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 15));

            // Directory selection controls
            directoryTextBox = new TextBox
            {
                Dock = DockStyle.Fill,
                Text = defaultDirectory
            };

            var browseButton = new Button
            {
                Dock = DockStyle.Fill,
                Text = "Browse",
                Margin = new Padding(5, 0, 0, 0)
            };
            browseButton.Click += BrowseButton_Click;

            topPanel.Controls.Add(directoryTextBox, 0, 0);
            topPanel.Controls.Add(browseButton, 1, 0);

            // Content panel
            var contentPanel = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 2,
                RowCount = 1,
                Margin = new Padding(0, 10, 0, 0)
            };
            contentPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 65));
            contentPanel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 35));

            // Content list view
            contentListView = new ListView
            {
                Dock = DockStyle.Fill,
                View = View.Details,
                FullRowSelect = true
            };
            contentListView.Columns.Add("Name", -2);
            contentListView.Columns.Add("Type", -2);
            contentListView.Columns.Add("DICOM Files", -2);
            contentListView.SelectedIndexChanged += ContentListView_SelectedIndexChanged;

            // Right panel
            rightPanel = new Panel
            {
                Dock = DockStyle.Fill,
                BorderStyle = BorderStyle.FixedSingle,
                Margin = new Padding(10, 0, 0, 0)
            };

            // Info label in right panel
            infoLabel = new Label
            {
                Location = new System.Drawing.Point(10, 10),
                AutoSize = false,
                Dock = DockStyle.Top,
                Height = 150
            };
            rightPanel.Controls.Add(infoLabel);

            // View DICOM button
            viewDicomButton = new Button
            {
                Dock = DockStyle.Bottom,
                Height = 30,
                Text = "View DICOM Images",
                Enabled = false,
                Margin = new Padding(10)
            };
            viewDicomButton.Click += ViewDicomButton_Click;
            rightPanel.Controls.Add(viewDicomButton);

            // Add controls to panels
            contentPanel.Controls.Add(contentListView, 0, 0);
            contentPanel.Controls.Add(rightPanel, 1, 0);

            // Add panels to main layout
            mainTableLayout.Controls.Add(topPanel, 0, 0);
            mainTableLayout.Controls.Add(contentPanel, 0, 1);

            // Add main layout to form
            Controls.Add(mainTableLayout);

            // Add resize event handler
            Resize += MainForm_Resize;
        }

        private void MainForm_Resize(object sender, EventArgs e)
        {
            // Adjust column widths in ListView
            if (contentListView.Columns.Count > 0)
            {
                int totalWidth = contentListView.ClientSize.Width;
                contentListView.Columns[0].Width = (int)(totalWidth * 0.5);  // Name: 50%
                contentListView.Columns[1].Width = (int)(totalWidth * 0.25); // Type: 25%
                contentListView.Columns[2].Width = (int)(totalWidth * 0.25); // DICOM Files: 25%
            }
        }

        private void BrowseButton_Click(object sender, EventArgs e)
        {
            using (WinForms.FolderBrowserDialog folderDialog = new FolderBrowserDialog())
            {
                folderDialog.SelectedPath = currentDirectory;
                folderDialog.ShowNewFolderButton = false;
                if (folderDialog.ShowDialog() == DialogResult.OK)
                {
                    currentDirectory = folderDialog.SelectedPath;
                    directoryTextBox.Text = currentDirectory;
                    LoadDirectory(currentDirectory);
                }
            }
        }

        private void LoadDirectory(string path)
        {
            contentListView.Items.Clear();
            infoLabel.Text = string.Empty;
            viewDicomButton.Enabled = false;

            // Get directories that directly contain .dcm files (no recursion)
            var directories = Enumerable.Empty<string>();
            try
            {
                directories = Directory.GetDirectories(path)
                    .Where(dir => Directory.GetFiles(dir, "*.dcm").Length > 0);
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading directory: {ex.Message}");
            }

            // Add directories with DICOM files to the list
            foreach (var dir in directories)
            {
                var dirInfo = new DirectoryInfo(dir);
                var dicomCount = Directory.GetFiles(dir, "*.dcm").Length;

                if (dicomCount <= 10)
                    continue;

                var item = new ListViewItem(new[]
                {
                    dirInfo.Name,
                    "Folder",
                    dicomCount.ToString()
                });
                item.Tag = dir;
                contentListView.Items.Add(item);
            }

            // Check if current directory has DICOM files
            var currentDirDicomFiles = new string[] { };
            try
            {
                currentDirDicomFiles = Directory.GetFiles(path, "*.dcm");
                if (currentDirDicomFiles.Length > 0)
                {
                    ShowDicomInfo(path);
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Error loading current directory: {ex.Message}");
            }
        }

        private void ContentListView_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (contentListView.SelectedItems.Count == 0)
                return;

            var selectedPath = contentListView.SelectedItems[0].Tag.ToString();
            ShowDicomInfo(selectedPath);
        }

        private void ShowDicomInfo(string path)
        {
            var dicomFiles = Directory.GetFiles(path, "*.dcm", SearchOption.TopDirectoryOnly);
            if (dicomFiles.Length == 0)
                return;

            var reader = new DicomReader(path);
            reader.LoadGlobalView();
            var displayManager = new DicomDisplayManager(reader);

            // Basic info display - you can expand this to show more DICOM metadata
            infoLabel.Text = $"{Path.GetFileName(path)}\n" +
                            $"Number of DICOM files: {dicomFiles.Length}\n" +
                            $"Total size: {GetDirectorySize(path) / 1024.0 / 1024.0:F2} MB\n\n" +
                            $"Patient ID: {displayManager.globalView.PatientID}\n" +
                            $"Patient Name: {displayManager.globalView.PatientName}\n" +
                            $"Patient Sex: {displayManager.globalView.PatientSex}\n" +
                            $"Modality: {displayManager.globalView.Modality}\n" +
                            $"Resolution: {displayManager.globalView.Rows} x {displayManager.globalView.Columns}";

            globalViewPictureBox?.Dispose();
            globalViewPictureBox = new PictureBox
            {
                Dock = DockStyle.Fill,
                SizeMode = PictureBoxSizeMode.Zoom
            };
            globalViewPictureBox.Image = displayManager.GetGlobalViewImage();
            rightPanel.Controls.Add(globalViewPictureBox);

            viewDicomButton.Enabled = true;
            viewDicomButton.Tag = path;
        }

        private long GetDirectorySize(string path)
        {
            return Directory.GetFiles(path, "*.dcm")
                           .Sum(file => new FileInfo(file).Length);
        }

        private void ViewDicomButton_Click(object sender, EventArgs e)
        {
            var path = viewDicomButton.Tag.ToString();
            var reader = new DicomReader(path);
            reader.LoadAllFiles();
            var viewerForm = new DicomViewerForm(reader);
            viewerForm.ShowDialog();
        }

    }
}
