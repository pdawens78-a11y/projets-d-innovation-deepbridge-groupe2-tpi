using DeepBridgeWindowsApp;
using System;
using System.Drawing;
using System.Windows.Forms;

public class MainForm : Form
{
    private Button dicomButton;
    private Button newPageButton;
    private Button creditsButton;
    private Label titleLabel;

    public MainForm()
    {
        InitializeComponents();
    }

    private void InitializeComponents()
    {
        // Form settings
        this.Size = new Size(1000, 600);
        this.MinimumSize = new Size(800, 400);
        this.Text = "DICOM Viewer - Menu";
        this.StartPosition = FormStartPosition.CenterScreen;
        this.BackColor = SystemColors.Control;

        // === Main Table Layout ===
        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 3,
            Padding = new Padding(20)
        };
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 40)); // title area
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 40)); // spacer / push buttons down
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 20)); // buttons row

        // === Title Label ===
        titleLabel = new Label
        {
            Text = "DEEP BRIDGE",
            Dock = DockStyle.Fill,
            Font = new Font("Segoe UI", 32, FontStyle.Bold),
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = Color.FromArgb(40, 40, 40)
        };
        layout.Controls.Add(titleLabel, 0, 0);

        // === Button Panel ===
        // === Button Panel ===
        var buttonPanel = new FlowLayoutPanel
        {
            AutoSize = true,                      // take size of children
            AutoSizeMode = AutoSizeMode.GrowAndShrink,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Dock = DockStyle.None,                // don't stretch full width
            Anchor = AnchorStyles.None,           // center it inside the cell
            Padding = new Padding(0)
        };

        Button CreateMenuButton(string text)
        {
            return new Button
            {
                Text = text,
                Font = new Font("Segoe UI", 14, FontStyle.Regular),
                Size = new Size(180, 60),
                FlatStyle = FlatStyle.Flat,
                Margin = new Padding(20, 0, 20, 0) // equal spacing between buttons
            };
        }

        dicomButton = CreateMenuButton("DicomViewer");
        dicomButton.Click += (s, e) =>
        {
            var browser = new DicomBrowserForm();
            browser.FormClosed += (s2, e2) => this.Show();
            this.Hide();
            browser.Show();
        };

        newPageButton = CreateMenuButton("RiskPrediction");
        newPageButton.Click += (s, e) =>
        {
            var newPage = new RiskPrediction();
            newPage.FormClosed += (s2, e2) => this.Show();
            this.Hide();
            newPage.Show();
        };

        //creditsButton = CreateMenuButton("Credits");
        //creditsButton.Click += (s, e) =>
        //{
        //    var credits = new CreditsForm();
        //    credits.FormClosed += (s2, e2) => this.Show();
        //    this.Hide();
        //    credits.Show();
        //};

        buttonPanel.Controls.Add(dicomButton);
        buttonPanel.Controls.Add(newPageButton);
        buttonPanel.Controls.Add(creditsButton);

        layout.Controls.Add(buttonPanel, 0, 2);

        // === Add layout to form ===
        this.Controls.Add(layout);
    }
}
